from datetime import datetime, timezone
from logging import getLogger

from fastapi import APIRouter, Depends, HTTPException
from pydantic import UUID4
from sqlalchemy import func, select, update

from warden.api.routes.dependencies.auth import (
    AdminUserDep,
    AuthConfigDep,
    ensure_user_is_authorized,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_config
from warden.api.schemas.sessions import CreateSession, SessionResponse
from warden.lib.config.config import QPUConfig
from warden.lib.models import Job, QPUCapacityLock, Session
from warden.lib.models.sessions import active_session_filter

logger = getLogger(__name__)
router = APIRouter(prefix="/sessions")


@router.post("")
async def create_session(
    payload: CreateSession,
    db_session: DBSessionDep,
    auth_config: AuthConfigDep,
    _admin: AdminUserDep,
    qpu_config: QPUConfig = Depends(get_qpu_config),
) -> SessionResponse:
    ensure_user_is_authorized(auth_config, str(payload.user_id))
    async with db_session.begin():
        await lock_qpu_capacity(db_session)
        existing = await active_session_for_job(
            db_session, str(payload.user_id), payload.slurm_job_id
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
            slurm_job_id=payload.slurm_job_id,
            qpu_slots=payload.qpu_slots,
        )
        db_session.add(new_session)
        await db_session.flush()
    return SessionResponse.from_model(new_session)


async def active_session_for_job(
    db_session: DBSessionDep, user_id: str, slurm_job_id: str
) -> Session | None:
    result = await db_session.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.slurm_job_id == slurm_job_id,
            active_session_filter(),
        )
    )
    return result.scalar_one_or_none()


async def lock_qpu_capacity(db_session: DBSessionDep) -> None:
    result = await db_session.execute(
        update(QPUCapacityLock)
        .where(QPUCapacityLock.id == 1)
        .values(revision=QPUCapacityLock.revision + 1)
    )
    if result.rowcount != 1:
        raise RuntimeError(
            "QPU capacity lock is missing; run the latest Warden database migration."
        )


async def active_qpu_slots(db_session: DBSessionDep) -> int:
    result = await db_session.execute(
        select(func.coalesce(func.sum(Session.qpu_slots), 0)).where(
            active_session_filter()
        )
    )
    return int(result.scalar_one())


@router.delete("/{id}")
async def revoke_session(
    id: UUID4,
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> SessionResponse:
    already_revoked = False
    async with db_session.begin():
        await lock_qpu_capacity(db_session)
        result = await db_session.execute(
            select(Session).where(Session.id == id).with_for_update(of=Session)
        )
        session_record = result.scalar_one_or_none()
        if session_record is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        already_revoked = session_record.revoked_at is not None
        if not already_revoked:
            session_record.revoked_at = datetime.now(timezone.utc)

    if already_revoked:
        return SessionResponse.from_model(session_record)

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
