"""Accounting information route"""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, select

from warden.api.routes.dependencies.auth import (
    AdminUserDep,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.schemas.acct import (
    AcctData,
    GetAcctRequest,
    GetAcctResponse,
    JobsSummary,
    JobSummaryStats,
    PaginationResponse,
    SessionsSummary,
)
from warden.lib.db.functions import duration_seconds
from warden.lib.models import Job, Session

logger = getLogger(__name__)
router = APIRouter(prefix="/acct")


@router.get("")
async def get_accounting_snapshot(
    params: Annotated[GetAcctRequest, Query()],
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> GetAcctResponse:
    """High-level accounting data"""

    # Base session filter
    session_filters = [Session.revoked_at >= params.start_datetime]

    if params.end_datetime:
        session_filters.append(Session.revoked_at < params.end_datetime)

    if params.user_ids:
        session_filters.append(Session.user_id.in_(params.user_ids))

    # Get total count for pagination
    total_count_stmt = select(func.count(func.distinct(Session.user_id))).where(
        and_(*session_filters)
    )
    total_result = await db_session.execute(total_count_stmt)
    total_count = total_result.scalar() or 0

    # Query to get sessions data aggregated by user_id
    sessions_stmt = (
        select(
            Session.user_id,
            func.count(Session.id).label("session_count"),
            func.coalesce(
                func.sum(
                    duration_seconds(Session.created_at, Session.revoked_at),
                ),
                0,
            ).label("total_session_duration"),
        )
        .where(and_(*session_filters))
        .group_by(Session.user_id)
        .order_by(Session.user_id)
        .offset(params.offset)
        .limit(params.limit)
    )

    sessions_result = await db_session.execute(sessions_stmt)
    sessions_data = sessions_result.fetchall()

    user_sessions_summary: dict[str, SessionsSummary] = {}

    for session_row in sessions_data:
        user_id = session_row.user_id
        user_sessions_summary[user_id] = SessionsSummary(
            count=session_row.session_count,
            total_duration=int(session_row.total_session_duration or 0),
        )

    if not user_sessions_summary:
        return GetAcctResponse(
            data=[],
            pagination=PaginationResponse.for_page(
                offset=params.offset, count=0, total=total_count
            ),
        )

    # Query to get jobs data aggregated by user_id and job status.
    # This aggregation has one row per (user, status), so it cannot share the
    # request's offset/limit with the sessions aggregation above. It is instead
    # restricted to the users on the page that query just returned.
    jobs_stmt = (
        select(
            Session.user_id,
            Job.status,
            func.count(Job.id).label("job_count"),
            func.coalesce(
                func.sum(duration_seconds(Job.started_at, Job.ended_at)), 0
            ).label("total_job_duration"),
        )
        .join(Session, Session.id == Job.session_id)
        .where(
            and_(*session_filters, Session.user_id.in_(user_sessions_summary.keys()))
        )
        .group_by(Session.user_id, Job.status)
        .order_by(Session.user_id)
    )

    jobs_result = await db_session.execute(jobs_stmt)
    jobs_data = jobs_result.fetchall()

    user_jobs_summaries: dict[str, JobsSummary] = {}

    for job_row in jobs_data:
        user_id = job_row.user_id
        if user_id not in user_jobs_summaries:
            user_jobs_summaries[user_id] = JobsSummary(count=0)
        user_jobs_summaries[user_id].count += job_row.job_count
        user_jobs_summaries[user_id].stats.append(
            JobSummaryStats(
                status=job_row.status,
                count=job_row.job_count,
                total_duration=int(job_row.total_job_duration or 0),
            )
        )

    # For each user, get job statistics
    acct_data_list = []

    for user_id in user_sessions_summary.keys():
        user_acct_data = AcctData(
            user_id=user_id,
            sessions=user_sessions_summary[user_id],
            jobs=user_jobs_summaries.get(user_id, JobsSummary(count=0)),
        )

        acct_data_list.append(user_acct_data)

    pagination_resp = PaginationResponse.for_page(
        offset=params.offset, count=len(acct_data_list), total=total_count
    )

    return GetAcctResponse(
        data=acct_data_list,
        pagination=pagination_resp,
    )
