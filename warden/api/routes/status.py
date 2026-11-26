from fastapi import APIRouter
from sqlalchemy import func, select

from warden.api.routes.dependencies.auth import AdminUserDep
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import APIQPUClient
from warden.api.schemas.status import (
    CurrentJob,
    OpenSession,
    StatusSummaryResponse,
    StatusResponse,
)
from warden.lib.models import Job, Session
from warden.lib.models.accessible import get_latest_accessibility_settings
from warden.lib.qpu_client import QPUClientRequestError

router = APIRouter(prefix="/status")


@router.get("")
async def get_status(
    db_session: DBSessionDep,
    _admin: AdminUserDep,
    client: APIQPUClient,
) -> StatusResponse:
    """Detailed live snapshot of Warden, restricted to admin users.

    Contains every field of `GET /status/summary`, plus:
    - `current_job`: the job currently running on the QPU, or null.
    - `open_sessions`: the sessions not yet revoked, oldest first.
    """
    resource_status = await _resource_status(db_session, client)

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
        **resource_status.model_dump(),
        current_job=current_job,
        open_sessions=open_sessions,
    )


@router.get("/summary")
async def get_status_summary(
    db_session: DBSessionDep,
    client: APIQPUClient,
) -> StatusSummaryResponse:
    """Aggregated live snapshot of Warden, used by QRMI's `status()`.

    Public: no authentication required.
    - `status`: "online" if Warden accepts jobs, "paused" otherwise
      (see `POST /accessible`).
    - `status_reason`: the message set with the latest accessibility setting.
    - `healthy`: true if the QPU is reachable and reports "UP", false if it is
      unreachable or reports anything else, null if it reports no status.
    - `busy`: true if a job is running or pending.
    - `pending_job_count`: number of jobs waiting to be scheduled.
    - `capacity`: always null, Warden has no notion of QPU slots yet.
    """
    return await _resource_status(db_session, client)


async def _resource_status(
    db_session: DBSessionDep, client: APIQPUClient
) -> StatusSummaryResponse:
    settings = await get_latest_accessibility_settings(db_session)

    try:
        qpu_status = await client.get_operational_status()
        healthy = qpu_status == "UP"
    except QPUClientRequestError:
        healthy = False
    except ValueError:
        healthy = None

    pending_job_count = await _pending_job_count(db_session)
    running_job_count = await _running_job_count(db_session)

    return StatusSummaryResponse(
        status="online" if settings.is_accessible else "paused",
        status_reason=settings.message,
        healthy=healthy,
        busy=bool(pending_job_count or running_job_count),
        pending_job_count=pending_job_count or 0,
        # Warden implements QPU slots
        capacity=None,
    )


async def _running_job_count(db_session: DBSessionDep):
    return await db_session.scalar(
        select(func.count(Job.id)).where(Job.status == "RUNNING")
    )


async def _pending_job_count(db_session: DBSessionDep):
    return await db_session.scalar(
        select(func.count(Job.id)).where(Job.status == "PENDING")
    )
