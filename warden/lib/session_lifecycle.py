import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import case, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from warden.lib.config import SessionConfig
from warden.lib.models import Job, QPUCapacityLock, Session
from warden.lib.models.sessions import active_session_filter

TERMINAL_JOB_STATUSES = ("ERROR", "DONE", "CANCELED")
logger = logging.getLogger(__name__)


def idle_deadline(config: SessionConfig, now: datetime | None = None) -> datetime:
    """Calculate a session idle deadline."""
    return (now or datetime.now(timezone.utc)) + timedelta(
        seconds=config.idle_timeout_s
    )


def absolute_deadline(config: SessionConfig, now: datetime | None = None) -> datetime:
    """Calculate a session absolute deadline."""
    return (now or datetime.now(timezone.utc)) + timedelta(
        seconds=config.max_lifetime_s
    )


async def lock_qpu_capacity(db_session: AsyncSession) -> None:
    """Serialize changes that affect available QPU capacity."""
    result = await db_session.execute(
        update(QPUCapacityLock)
        .where(QPUCapacityLock.id == 1)
        .values(revision=QPUCapacityLock.revision + 1)
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        raise RuntimeError(
            "QPU capacity lock is missing; run the latest Warden database migration."
        )


async def has_nonterminal_jobs(db_session: AsyncSession, session_id: UUID) -> bool:
    """Return whether a session has pending or running jobs."""
    result = await db_session.execute(
        select(Job.id)
        .where(
            Job.session_id == session_id,
            Job.status.not_in(TERMINAL_JOB_STATUSES),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def session_is_expired(
    db_session: AsyncSession,
    session_record: Session,
    now: datetime | None = None,
) -> bool:
    """Return whether a session has reached an applicable deadline."""
    current = now or datetime.now(timezone.utc)
    if _as_utc(session_record.expires_at) <= current:
        return True
    if _as_utc(session_record.idle_expires_at) > current:
        return False
    return not await has_nonterminal_jobs(db_session, session_record.id)


async def revoke_session_record(
    db_session: AsyncSession,
    session_record: Session,
    reason: str,
    now: datetime | None = None,
) -> bool:
    """Revoke a session and request cancellation of its unfinished jobs."""
    if session_record.revoked_at is not None:
        return False

    revoked_at = now or datetime.now(timezone.utc)
    session_record.revoked_at = revoked_at
    session_record.revocation_reason = reason
    # Atomic claim: same pattern as `jobs.py::cancel_job`, the status and
    # cancelability guards are re-evaluated against the live rows by this
    # single UPDATE, so there's no read-then-write gap for a concurrent
    # scheduler pickup.
    result = cast(
        CursorResult[Any],
        await db_session.execute(
            update(Job)
            .where(
                Job.session_id == session_record.id,
                Job.status.not_in(TERMINAL_JOB_STATUSES),
                Job.canceled_at.is_(None),
            )
            .values(
                canceled_at=revoked_at,
                status=case((Job.scheduled_at.is_(None), "CANCELED"), else_=Job.status),
            )
        ),
    )
    if result.rowcount > 0:
        logger.info(
            "Canceled %d job(s) attached to revoked session '%s'",
            result.rowcount,
            session_record.id,
        )
    return True


async def expire_due_sessions(
    db_session: AsyncSession, now: datetime | None = None
) -> int:
    """Revoke sessions whose applicable deadline has passed."""
    current = now or datetime.now(timezone.utc)
    result = await db_session.execute(
        select(Session)
        .where(
            active_session_filter(),
            or_(
                Session.expires_at <= current,
                Session.idle_expires_at <= current,
            ),
        )
        .with_for_update(of=Session)
    )
    expired = 0
    for session_record in result.scalars():
        if _as_utc(session_record.expires_at) <= current:
            reason = "max_lifetime_expired"
        elif await has_nonterminal_jobs(db_session, session_record.id):
            continue
        else:
            reason = "idle_timeout"
        if await revoke_session_record(db_session, session_record, reason, current):
            expired += 1
    return expired


async def session_reaper(
    config: SessionConfig,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Periodically revoke expired sessions."""
    while True:
        try:
            async with session_factory() as db_session:
                async with db_session.begin():
                    await lock_qpu_capacity(db_session)
                    expired = await expire_due_sessions(db_session)
            if expired:
                logger.info("Revoked %s expired session(s)", expired)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Session expiry check failed")
        await asyncio.sleep(config.reaper_interval_s)


def _as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
