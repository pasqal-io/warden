"""Main logic of the scheduler"""

import asyncio
from asyncio import Queue
import signal
import logging.config

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession

from warden.lib.config import Config
from warden.lib.qpu_client import QPUJobInfo
from warden.lib.db.database import build_db_url
from warden.lib.models import Job

from warden.scheduler.strategy import schedulers
from warden.scheduler.worker import LocalQPUWorker

QUEUE_MAXSIZE = 0

logger = logging.getLogger("warden.scheduler")


async def run_scheduler(engine: AsyncEngine, conf: Config):
    """Scheduler main logic

    Infinite loop:
    - Get with the configure scheduler strategy the next job to execute.
        - If no job to execute, sleep for `db_polling_interval_s` and continue
    - Schedules two tasks that communicate data through an async queue:
        - `db_commit_task`: infinite loop coroutine to update job information to the database
        - `worker_task`: worker coroutine that handles job execution on the qpu
    - Awaits the end of the job execution in `worker_task` task
    - Awaits that all job updates 
    - Cancels `db_commit_task` task that is no longer needed

    Infinite loop gets canceled by `main_async` when stop signal is received.
    """
    logger.info("Scheduler running.")

    qpu_worker = LocalQPUWorker(conf=conf)
    queue: Queue[QPUJobInfo] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)

    strategy = conf.scheduler.strategy
    logger.debug(f"Scheduler using '{strategy}' strategy")

    while True:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            job = await schedulers[strategy].get_next_job(session)
            if job is None:
                sleep_time = conf.scheduler.db_polling_interval_s
                logger.debug(f"No job to schedule, sleeping {sleep_time}")
                await asyncio.sleep(sleep_time)
                continue
            logger.info(f"Scheduling next job: {job.id}")

            # DB commit loop
            db_commit_task = asyncio.create_task(
                async_commit(queue=queue, session=session, job=job)
            )

            # QPU job execution
            worker_task = asyncio.create_task(
                qpu_worker.execute_job(
                    queue=queue,
                    nb_run=job.shots,
                    sequence=job.sequence,
                    batch_id=job.session.slurm_job_id,
                )
            )

            # Await end of job execution
            await worker_task
            # Await that all updates are commited to DB
            await queue.join()
            # Kill DB commit loop
            db_commit_task.cancel()

            logger.info(f"Job {job.id} ended with status: {job.status}")


async def async_commit(queue: Queue[QPUJobInfo], session: AsyncSession, job: Job):
    """Async coroutine loop to continuously Job info during execution"""
    while True:
        qpu_job = await queue.get()

        logger.debug(f"Updating job {job.id} on db")
        _write_info_to_job(job, qpu_job)
        await session.commit()

        # Signals that data received in `queue.get()` was processed
        queue.task_done()
        logger.debug(f"Job {job.id} updated")


def _write_info_to_job(job: Job, qpu_job: QPUJobInfo) -> None:
    """Write job update to ORM db object"""

    job.backend_id = qpu_job.uid
    job.status = qpu_job.status
    job.started_at = qpu_job.start_datetime
    job.ended_at = qpu_job.end_datetime
    job.results = qpu_job.result


async def shutdown(engine: AsyncEngine):
    """Cleanup tasks and close DB connections."""

    logger.info("Closing database connections...")
    await engine.dispose()

    logger.info("Stopping all tasks")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]

    await asyncio.gather(*tasks, return_exceptions=True)


async def main_async(conf=Config()):
    """Main asyncio logic"""
    logging.config.dictConfig(config=conf.logging)
    engine = create_async_engine(build_db_url(conf.database))
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: stop_event.set())

    try:
        logger.info("Starting scheduler (Press Ctrl+C to exit)...")
        loop.create_task(run_scheduler(engine, conf))
        await stop_event.wait()
    finally:
        await shutdown(engine)
        logger.info("Scheduler shutdown complete.")


def main():
    """Entrypoint"""
    asyncio.run(main_async())
