from datetime import datetime, timezone
from logging import getLogger
from typing import cast

from fastapi import APIRouter, HTTPException
from pydantic import UUID4
from sqlalchemy import CursorResult, case, select, update

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
        # Atomic claim: same pattern as `jobs.py::cancel_job`, the status
        # and cancelability guards are re-evaluated against the live row by
        # this single UPDATE, so there's no read-then-write gap for a
        # concurrent scheduler pickup.
        result = cast(
            CursorResult,
            await db_session.execute(
                update(Job)
                .where(
                    Job.session_id == session_record.id,
                    Job.status.not_in(("CANCELED", "DONE", "ERROR")),
                    Job.canceled_at.is_(None),
                )
                .values(
                    canceled_at=datetime.now(timezone.utc),
                    status=case(
                        (Job.scheduled_at.is_(None), "CANCELED"), else_=Job.status
                    ),
                )
            ),
        )
        if result.rowcount > 0:
            logger.info(
                "Canceled %d job(s) attached to revoked session '%s'",
                result.rowcount,
                session_record.id,
            )

    return SessionResponse.from_model(session_record)
