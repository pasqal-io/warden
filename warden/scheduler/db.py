"""DB commit async worker"""

import logging

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from warden.lib.models import Job
from warden.scheduler.types import UpdateQueue

logger = logging.getLogger(__name__)


async def job_update_commiter(
    job_id: int, queue: UpdateQueue, session_factory: async_sessionmaker[AsyncSession]
):
    """Consumes Job Updates to db"""
    while True:
        job_update = await queue.get()

        async with session_factory() as session:
            try:
                async with session.begin():
                    stmt = (
                        update(Job)
                        .where(Job.id == job_id)
                        .values(
                            {
                                "backend_id": job_update.backend_id,
                                "status": job_update.status,
                                "results": job_update.result,
                                "started_at": job_update.started_at,
                                "ended_at": job_update.ended_at,
                                "logs": func.coalesce(Job.logs, "")
                                + job_update.new_logs,
                            }
                        )
                    )
                    await session.execute(stmt)
                logger.debug(f"Job {job_id} updated in db")
            except Exception as e:
                logger.error(f"DB Update failed: {e}")
            finally:
                queue.task_done()
