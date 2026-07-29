"""Accounting information route"""

from logging import getLogger

from fastapi import APIRouter
from sqlalchemy import and_, func, select

from warden.api.routes.dependencies.auth import (
    AdminUserDep,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.schemas.acct import (
    AcctData,
    GetAcctJobsRequestQueryParams,
    GetAcctJobsResponse,
    GetAcctRequestQueryParams,
    GetAcctResponse,
    GetAcctSessionsRequestQueryParams,
    GetAcctSessionsResponse,
    JobData,
    JobsSummary,
    JobSummaryStats,
    PaginationResponse,
    SessionData,
    SessionsSummary,
)
from warden.lib.models import Job, Session

logger = getLogger(__name__)
router = APIRouter(prefix="/accounting")


@router.get("")
async def get_accounting_snapshot(
    params: GetAcctRequestQueryParams,
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> GetAcctResponse:
    """Per-user accounting summary.

    Aggregates session counts/duration and job counts/execution/wait time
    and status per user, for sessions revoked within the requested time window.
    One row per user paginated over the distinct set of users.
    """

    # Base session filter
    db_query_filters = params.build_db_query_filters()

    # Get total data row count for pagination
    total_count_stmt = select(func.count(func.distinct(Session.user_id))).where(
        and_(*db_query_filters)
    )
    total_result = await db_session.execute(total_count_stmt)
    total_count = total_result.scalar() or 0

    # Query to get sessions data aggregated by user_id
    sessions_stmt = (
        select(
            Session.user_id,
            func.count(Session.id).label("session_count"),
            func.sum(Session.duration).label("total_session_duration"),
        )
        .where(and_(*db_query_filters))
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
            func.coalesce(func.sum(Job.execution_time), 0).label("execution_time"),
            func.coalesce(func.sum(Job.wait_time), 0).label("wait_time"),
        )
        .join(Session, Session.id == Job.session_id)
        .where(
            and_(*db_query_filters, Session.user_id.in_(user_sessions_summary.keys()))
        )
        .group_by(Session.user_id, Job.status)
        .order_by(Session.user_id)
    )

    jobs_result = await db_session.execute(jobs_stmt)
    jobs_data = jobs_result.fetchall()

    user_jobs_summaries: dict[str, JobsSummary] = {}

    for job_row in jobs_data:
        user_id = job_row.user_id
        row_execution_time = int(job_row.execution_time)
        row_wait_time = int(job_row.wait_time)
        if user_id not in user_jobs_summaries:
            user_jobs_summaries[user_id] = JobsSummary(count=0)
        user_jobs_summaries[user_id].count += job_row.job_count
        user_jobs_summaries[user_id].execution_time += row_execution_time
        user_jobs_summaries[user_id].wait_time += row_wait_time
        user_jobs_summaries[user_id].stats.append(
            JobSummaryStats(
                status=job_row.status,
                count=job_row.job_count,
                execution_time=row_execution_time,
                wait_time=row_wait_time,
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


@router.get("/sessions")
async def get_sessions_accounting(
    params: GetAcctSessionsRequestQueryParams,
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> GetAcctSessionsResponse:
    """Per-session accounting report.

    Returns one row per session revoked within the requested time window,
    with its duration and job count. Can additionally be filtered by
    `slurm_job_id`.
    """

    # Base session filter
    db_query_filters = params.build_db_query_filters()

    # Get total count for pagination
    total_count_stmt = select(func.count(Session.id)).where(and_(*db_query_filters))
    total_result = await db_session.execute(total_count_stmt)
    total_count = total_result.scalar() or 0

    if total_count == 0:
        return GetAcctSessionsResponse(
            data=[],
            pagination=PaginationResponse.for_page(
                offset=params.offset, count=0, total=total_count
            ),
        )

    # Query to get sessions data aggregated by user_id
    sessions_stmt = (
        select(
            Session,
            Session.duration,
            func.count(Job.id).label("job_count"),
        )
        .outerjoin(Job, Job.session_id == Session.id)
        .group_by(Session.id)
        .where(and_(*db_query_filters))
        .order_by(Session.created_at)
        .offset(params.offset)
        .limit(params.limit)
    )

    sessions_result = await db_session.execute(sessions_stmt)
    sessions_data = sessions_result.fetchall()

    return_data = []
    for session_row in sessions_data:
        session_data = SessionData.from_session_record(session_row.Session)
        session_data.total_duration = int(session_row.duration or 0)
        session_data.jobs_count = int(session_row.job_count)
        return_data.append(session_data)
    return GetAcctSessionsResponse(
        data=return_data,
        pagination=PaginationResponse.for_page(
            offset=params.offset, count=len(return_data), total=total_count
        ),
    )


@router.get("/jobs")
async def get_jobs_accounting(
    params: GetAcctJobsRequestQueryParams,
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> GetAcctJobsResponse:
    """Per-job accounting report.

    Returns one row per job **belonging to a session revoked within the
    requested time window** (same session-based time filtering as the other
    accounting routes, for consistency). Can additionally be filtered by
    `session_id` and job `status`.
    """

    # Base session filter
    db_query_filters = params.build_db_query_filters()

    # Get total count for pagination
    total_count_stmt = (
        select(func.count(Job.id))
        .join(Session, Session.id == Job.session_id)
        .where(and_(*db_query_filters))
    )

    total_result = await db_session.execute(total_count_stmt)
    total_count = total_result.scalar() or 0

    if total_count == 0:
        return GetAcctJobsResponse(
            data=[],
            pagination=PaginationResponse.for_page(
                offset=params.offset, count=0, total=total_count
            ),
        )

    jobs_stmt = (
        select(
            Job,
            Job.execution_time,
            Job.wait_time,
        )
        .join(Session, Session.id == Job.session_id)
        .where(and_(*db_query_filters))
        .order_by(Job.created_at)
        .offset(params.offset)
        .limit(params.limit)
    )

    jobs_result = await db_session.execute(jobs_stmt)
    jobs_data = jobs_result.fetchall()

    return_data = []
    for job_row in jobs_data:
        job_data = JobData(
            id=job_row.Job.id,
            user_id=job_row.Job.user_id,
            session_id=job_row.Job.session_id,
            status=job_row.Job.status,
            shots=job_row.Job.shots,
            execution_time=int(job_row.execution_time or 0),
            wait_time=int(job_row.wait_time or 0),
        )
        return_data.append(job_data)
    return GetAcctJobsResponse(
        data=return_data,
        pagination=PaginationResponse.for_page(
            offset=params.offset, count=len(return_data), total=total_count
        ),
    )
