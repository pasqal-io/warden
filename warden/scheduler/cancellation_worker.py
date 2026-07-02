"""Job cancel worker"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from warden.lib.config import Config
from warden.lib.models import Job
from warden.lib.qpu_client import JobCancelationError, QPUClient, QPUClientRequestError

logger = logging.getLogger(__name__)


async def cancellation_worker(
    conf: Config, session_factory: async_sessionmaker[AsyncSession]
):
    """Check cancellation queue"""

    client = QPUClient(qpu_conf=conf.qpu)
    sleep_interval = conf.scheduler.db_polling_interval_s

    queue_stmt = (
        select(Job)
        .where(
            Job.status.in_(["RUNNING", "PENDING"]),
            Job.backend_id.is_not(None),
            Job.canceled_at.is_not(None),
        )
        .limit(1)
    )

    while True:
        async with session_factory() as session:
            job = (await session.execute(queue_stmt)).scalar_one_or_none()

            if not job:
                logger.debug(f"No job to cancel, sleeping {sleep_interval}")
                await asyncio.sleep(sleep_interval)
                continue

            logger.info("Cancelling job '%s'", job.id)

            try:
                if job.backend_id is None:
                    raise JobCancelationError("No backend ID foud in db")

                client.cancel_job(int(job.backend_id))
                logger.debug(
                    "Sent cancel request to QPU for job '%s' with QPU id '%s'",
                    job.id,
                    job.backend_id,
                )
            except (JobCancelationError, QPUClientRequestError) as e:
                logger.error(
                    "Can't cancel job '%s' with QPU id '%s':%s",
                    job.id,
                    job.backend_id,
                    e,
                )

            while job.status not in ("ERROR", "DONE", "CANCELED"):
                logger.debug("Waiting for job '%s' to end", job.id)
                await asyncio.sleep(sleep_interval)
                await session.refresh(job)
            logger.debug("Job '%s' ended", job.id)
