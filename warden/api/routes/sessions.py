from datetime import datetime, timezone
from logging import getLogger

from fastapi import APIRouter, HTTPException
from pydantic import UUID4
from sqlalchemy import select

from warden.api.routes.dependencies.auth import (
    AdminUserDep,
    AuthConfigDep,
    ensure_user_is_authorized,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.schemas.sessions import CreateSession, SessionResponse
from warden.lib.models import Job, Session

logger = getLogger(__name__)
router = APIRouter(prefix="/sessions")


@router.post("")
async def create_session(
    payload: CreateSession,
    db_session: DBSessionDep,
    auth_config: AuthConfigDep,
    _admin: AdminUserDep,
) -> SessionResponse:
    ensure_user_is_authorized(auth_config, str(payload.user_id))
    new_session = Session(
        user_id=str(payload.user_id),
        slurm_job_id=payload.slurm_job_id,
    )
    db_session.add(new_session)
    await db_session.flush()
    await db_session.commit()
    return SessionResponse.from_model(new_session)


@router.delete("/{id}")
async def revoke_session(
    id: UUID4,
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> SessionResponse:
    result = await db_session.execute(select(Session).where(Session.id == id))
    session_record = result.scalar_one_or_none()
    if session_record is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    session_record.revoked_at = datetime.now(timezone.utc)
    await db_session.flush()
    await db_session.commit()

    async with db_session.begin():
        result = await db_session.execute(
            select(Job)
            .where(
                Job.session_id == session_record.id,
                Job.status.not_in(("ERROR", "DONE", "CANCELED")),
                Job.canceled_at.is_(None),
            )
            .with_for_update(of=Job)
        )
        jobs_to_cancel = result.scalars()
        for job in jobs_to_cancel:
            logger.info(
                "Cancelling job '%s' attached to session %s", job.id, session_record.id
            )
            job.canceled_at = datetime.now(timezone.utc)
            # Not yet started by the worker
            if job.scheduled_at is None:
                # Set job to cancel
                job.status = "CANCELED"
            # Releases nowait

    return SessionResponse.from_model(session_record)
