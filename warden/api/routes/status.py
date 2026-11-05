from fastapi import APIRouter
from sqlalchemy import func, select

from warden.api.routes.dependencies.auth import AdminUserDep
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.schemas.status import (
    CurrentJob,
    OpenSession,
    ResourceStatusResponse,
    StatusResponse,
)
from warden.lib.models import Job, Session
from warden.lib.models.accessible import get_latest_accessibility_settings

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
    - open sessions

    Restricted to admin users.
    """
    pending_jobs_count = await _pending_job_count(db_session)

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
        select(Session).where(Session.revoked_at.is_(None)).order_by(Session.created_at)
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


@router.get("/resource")
async def get_resource_status(db_session: DBSessionDep) -> ResourceStatusResponse:
    """Warden endpoint for qrmi 'status' interface.

    Unauthenticated like `/accessible`, which it supersedes for QRMI: it only
    exposes aggregate counts, unlike the admin-only `/status` snapshot
    above.

    `status` follows `/accessible` only: `offline` when an admin made Warden
    inaccessible, `online` otherwise. The QPU is not probed, since a transient
    QPU error would wrongly take the resource offline.
    """
    settings = await get_latest_accessibility_settings(db_session)

    pending_job_count = await _pending_job_count(db_session)
    running_job_count = await db_session.scalar(
        select(func.count(Job.id)).where(Job.status == "RUNNING")
    )

    return ResourceStatusResponse(
        # paused/offline interpreted similarly in hres plugin for the moment
        status="online" if settings.is_accessible else "paused",
        status_reason=settings.message,
        # None until QPU health is better defined.
        healthy=None,
        busy=bool(pending_job_count or running_job_count),
        pending_job_count=pending_job_count or 0,
        # None until Warden implements QPU slots
        capacity=None,
    )


async def _pending_job_count(db_session):
    return await db_session.scalar(
        select(func.count(Job.id)).where(Job.status == "PENDING")
    )
