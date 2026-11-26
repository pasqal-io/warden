from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from warden.api.routes.dependencies.auth import AdminUserDep
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_client
from warden.api.schemas.status import (
    CurrentJob,
    OpenSession,
    ResourceStatusResponse,
    StatusResponse,
)
from warden.lib.models import Job, Session
from warden.lib.models.accessible import get_latest_accessibility_settings
from warden.lib.qpu_client import QPUClient, QPUClientRequestError

router = APIRouter(prefix="/status")


@router.get("")
async def get_status(
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> StatusResponse:
    """
    Provide in-depth live snapshot of Warden's current activity:
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
async def get_resource_status(
    db_session: DBSessionDep,
    client: QPUClient = Depends(get_qpu_client),
) -> ResourceStatusResponse:
    """
    Provide aggregated live snapshot of Warden's state:
    - current Warden availability
    - busy status
        - running jobs
        - scheduling pending jobs
    - healthy status
        - 'True' if QPU reachable and 'UP'
        - 'False' if QPU unreachable or reachable and 'DOWN'
    - count of pending jobs
    -
    """
    settings = await get_latest_accessibility_settings(db_session)

    try:
        qpu_status = await client.get_operational_status()
        healthy = qpu_status == "UP"
    except QPUClientRequestError:
        healthy = False
    except ValueError:
        healthy = None

    pending_job_count = await _pending_job_count(db_session)
    running_job_count = await _has_running_job(db_session)

    return ResourceStatusResponse(
        # paused/offline interpreted similarly in hres plugin for the moment
        status="online" if settings.is_accessible else "paused",
        status_reason=settings.message,
        healthy=healthy,
        busy=bool(pending_job_count or running_job_count),
        pending_job_count=pending_job_count or 0,
        # None until Warden implements QPU slots
        capacity=None,
    )


async def _has_running_job(db_session: DBSessionDep):
    return await db_session.scalar(
        select(func.count(Job.id)).where(Job.status == "RUNNING")
    )


async def _pending_job_count(db_session: DBSessionDep):
    return await db_session.scalar(
        select(func.count(Job.id)).where(Job.status == "PENDING")
    )
