from fastapi import APIRouter
from sqlalchemy import func, select

from warden.api.routes.dependencies.auth import AdminUserDep
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.schemas.status import CurrentJob, OpenSession, StatusResponse
from warden.lib.models import Job, Session

router = APIRouter(prefix="/status")


@router.get("")
async def get_status(
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> StatusResponse:
    """
    Provide live snapshot of Warden's current activity:
    - count of pending jobs
    - the job currently executing
    - open sessions.
    """
    pending_jobs_count = await db_session.scalar(
        select(func.count(Job.id)).where(Job.status == "PENDING")
    )

    running_job = await db_session.scalar(select(Job).where(Job.status == "RUNNING"))
    current_job = (
        CurrentJob(
            id=running_job.id,
            session_id=running_job.session_id,
            user_id=running_job.user_id,
            started_at=running_job.started_at,
            backend_id=running_job.backend_id,
        )
        if running_job is not None
        else None
    )

    open_sessions_result = await db_session.execute(
        select(Session).where(Session.revoked_at.is_(None))
    )
    open_sessions = [
        OpenSession(
            id=session.id,
            user_id=session.user_id,
            created_at=session.created_at,
            slurm_job_id=session.slurm_job_id,
        )
        for session in open_sessions_result.scalars()
    ]

    return StatusResponse(
        pending_jobs_count=pending_jobs_count or 0,
        current_job=current_job,
        open_sessions=open_sessions,
    )
