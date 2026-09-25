from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import UUID4
from sqlalchemy import select

from warden.api.routes.dependencies.auth import (
    AdminUserDep,
    AuthConfigDep,
    ensure_user_is_authorized,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_config
from warden.api.routes.dependencies.session_config import SessionConfigDep
from warden.api.schemas.sessions import CreateSession, SessionResponse
from warden.lib.config.config import QPUConfig
from warden.lib.models import Session
from warden.lib.models.sessions import active_session_filter
from warden.lib.session_lifecycle import (
    absolute_deadline,
    active_qpu_slots,
    expire_due_sessions,
    idle_deadline,
    lock_qpu_capacity,
    revoke_session_record,
)

router = APIRouter(prefix="/sessions")


@router.post("")
async def create_session(
    payload: CreateSession,
    db_session: DBSessionDep,
    auth_config: AuthConfigDep,
    _admin: AdminUserDep,
    session_config: SessionConfigDep,
    qpu_config: QPUConfig = Depends(get_qpu_config),
) -> SessionResponse:
    """Create a session or return the matching session after an adapter retry."""
    ensure_user_is_authorized(auth_config, str(payload.user_id))
    async with db_session.begin():
        await lock_qpu_capacity(db_session)
        await expire_due_sessions(db_session)
        existing = await active_session_for_job(
            db_session,
            str(payload.user_id),
            payload.scheduler_job_id,
        )
        if existing is not None:
            if existing.qpu_slots != payload.qpu_slots:
                raise HTTPException(
                    status_code=409,
                    detail="An active session already exists for this scheduler job with different parameters.",
                )
            return SessionResponse.from_model(existing)
        if qpu_config.qpu_slots_total is not None:
            used = await active_qpu_slots(db_session)
            if used + payload.qpu_slots > qpu_config.qpu_slots_total:
                raise HTTPException(
                    status_code=409,
                    detail="Not enough QPU slots available.",
                )
        new_session = Session(
            user_id=str(payload.user_id),
            scheduler_job_id=payload.scheduler_job_id,
            qpu_slots=payload.qpu_slots,
            idle_expires_at=idle_deadline(session_config),
            expires_at=absolute_deadline(session_config),
        )
        db_session.add(new_session)
        await db_session.flush()
    return SessionResponse.from_model(new_session)


async def active_session_for_job(
    db_session: DBSessionDep,
    user_id: str,
    scheduler_job_id: str,
) -> Session | None:
    result = await db_session.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.scheduler_job_id == scheduler_job_id,
            active_session_filter(),
        )
    )
    return result.scalar_one_or_none()


@router.get("")
async def list_sessions(
    db_session: DBSessionDep,
    _admin: AdminUserDep,
    user_id: str | None = None,
    scheduler_job_id: str | None = None,
    active: bool | None = None,
) -> list[SessionResponse]:
    """List sessions for administrator recovery."""
    query = select(Session).order_by(Session.created_at.desc())
    if user_id is not None:
        query = query.where(Session.user_id == user_id)
    if scheduler_job_id is not None:
        query = query.where(Session.scheduler_job_id == scheduler_job_id)
    if active is not None:
        query = query.where(
            active_session_filter() if active else ~active_session_filter()
        )
    result = await db_session.execute(query)
    return [SessionResponse.from_model(record) for record in result.scalars()]


@router.delete("")
async def revoke_session(
    db_session: DBSessionDep,
    _admin: AdminUserDep,
    session_id: UUID4 | None = Header(default=None, alias="X-Warden-Session"),
) -> SessionResponse:
    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing 'X-Warden-Session' header.",
        )
    return await _revoke(db_session, session_id)


@router.delete("/{id}", deprecated=True)
async def revoke_session_by_path(
    id: UUID4,
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> SessionResponse:
    """Revoke a session for clients that predate the X-Warden-Session header.

    Prefer `DELETE /sessions`: the session ID is a credential and URLs end up
    in access logs.
    """
    return await _revoke(db_session, id)


async def _revoke(db_session: DBSessionDep, session_id: UUID4) -> SessionResponse:
    async with db_session.begin():
        await lock_qpu_capacity(db_session)
        result = await db_session.execute(
            select(Session).where(Session.id == session_id).with_for_update(of=Session)
        )
        session_record = result.scalar_one_or_none()
        if session_record is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        await revoke_session_record(db_session, session_record, "manual")

    return SessionResponse.from_model(session_record)
