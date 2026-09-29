"""DB commit async worker"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from warden.lib.models import Job, Session
from warden.lib.session_lifecycle import TERMINAL_JOB_STATUSES
from warden.scheduler.types import JobUpdateQueue

logger = logging.getLogger(__name__)


async def job_update_commiter(
    job_id: int,
    queue: JobUpdateQueue,
    session_factory: async_sessionmaker[AsyncSession],
    session_idle_timeout_s: int,
):
    """Consumes Job Updates to db"""
    while True:
        job_update = await queue.get()

        async with session_factory() as session:
            values_update = {
                "backend_id": job_update.backend_id,
                "status": job_update.status,
                "results": job_update.result,
                "started_at": job_update.started_at,
                "ended_at": job_update.ended_at,
            }
            # Prevent updating None values to DB
            values_update = {k: v for (k, v) in values_update.items() if v is not None}
            stmt = (
                update(Job)
                .where(Job.id == job_id)
                .values(
                    {
                        **values_update,
                        "logs": func.coalesce(Job.logs, "") + job_update.new_logs,
                    }
                )
            )
            try:
                async with session.begin():
                    await session.execute(stmt)
                logger.debug(f"Job {job_id} updated in db")
            except Exception as e:
                logger.error(f"DB Update failed: {e}")
            else:
                if job_update.status in TERMINAL_JOB_STATUSES:
                    await _refresh_session_idle_deadline(
                        session, job_id, session_idle_timeout_s
                    )
            finally:
                queue.task_done()


async def _refresh_session_idle_deadline(
    session: AsyncSession, job_id: int, session_idle_timeout_s: int
) -> None:
    """Restart the idle timeout of the session of a finished job.

    Runs in its own transaction after the job update: holding the job row
    while locking the session would invert the session-then-job lock order of
    session revocation and could deadlock.
    """
    try:
        # Plain read first: a subquery inside the UPDATE would lock the job
        # row on MariaDB.
        session_id = (
            await session.execute(select(Job.session_id).where(Job.id == job_id))
        ).scalar_one()
        await session.commit()
        async with session.begin():
            await session.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(
                    idle_expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=session_idle_timeout_s)
                )
            )
    except Exception as e:
        logger.error(f"Session idle deadline update failed for job {job_id}: {e}")
