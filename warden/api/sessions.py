from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import UUID4
from sqlalchemy import Select
from warden.db.database import DBSessionDep
from logging import getLogger

from warden.api.auth.auth import verify_root
from warden.models.sessions import Session
from warden.schemas.sessions import CreateSession, SessionResponse

logger = getLogger(__name__)
router = APIRouter(prefix="/sessions")


@router.post("")
async def create_session(
    payload: CreateSession,
    db_session: DBSessionDep,
    _=Depends(verify_root),
) -> SessionResponse:
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
    _=Depends(verify_root),
) -> SessionResponse:
    result = await db_session.execute(Select(Session).where(Session.id == id))
    session_record = result.scalar_one_or_none()
    if session_record is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    session_record.revoked_at = datetime.now(timezone.utc)
    await db_session.flush()
    await db_session.commit()
    return SessionResponse.from_model(session_record)
