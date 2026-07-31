"""Session-idle watchdog: revokes sessions with no new job in a configurable window."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from warden.lib.config import Config
from warden.lib.models import Job, Session
from warden.lib.sessions import revoke_session_and_cancel_jobs

logger = logging.getLogger(__name__)


async def session_watchdog(
    conf: Config, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Revoke sessions that haven't had a new job created within the idle timeout.

    Infinite loop, meant to run alongside the scheduler and cancellation worker.
    A `session_idle_timeout_s` of -1 disables the watchdog.
    """
    sleep_interval = conf.scheduler.db_polling_interval_s
    timeout_s = conf.scheduler.session_idle_timeout_s

    while True:
        if timeout_s < 0:
            await asyncio.sleep(sleep_interval)
            continue

        async with session_factory() as db_session:
            sessions = (
                (
                    await db_session.execute(
                        select(Session).where(Session.revoked_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )

            if sessions:
                last_job_at_by_session = dict(
                    (
                        await db_session.execute(
                            select(Job.session_id, func.max(Job.created_at)).group_by(
                                Job.session_id
                            )
                        )
                    ).all()
                )

                now = datetime.now(timezone.utc)
                for session_record in sessions:
                    last_activity = last_job_at_by_session.get(
                        session_record.id, session_record.created_at
                    )
                    if last_activity.tzinfo is None:
                        # ponytail: sqlite/mariadb drivers hand back naive
                        # datetimes for DateTime(timezone=True) columns even
                        # though every write here is UTC; normalize on read.
                        last_activity = last_activity.replace(tzinfo=timezone.utc)
                    if (now - last_activity).total_seconds() > timeout_s:
                        logger.info(
                            "Revoking session '%s': no new job for over %ss",
                            session_record.id,
                            timeout_s,
                        )
                        await revoke_session_and_cancel_jobs(db_session, session_record)

        await asyncio.sleep(sleep_interval)
