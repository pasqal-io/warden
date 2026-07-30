"""Main logic of the scheduler"""

import asyncio
import logging.config
import signal
from contextlib import suppress

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from warden.lib.config import Config
from warden.lib.db.database import build_db_url
from warden.lib.models import Job
from warden.scheduler.cancellation_worker import cancellation_worker
from warden.scheduler.db import job_update_commiter
from warden.scheduler.strategy import schedulers
from warden.scheduler.types import JobUpdateQueue
from warden.scheduler.worker import LocalQPUWorker

QUEUE_MAXSIZE = 0

# Fixed bound, make it configurable if a slow DB ever trips it
DB_FLUSH_TIMEOUT_S = 10

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
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    strategy = conf.scheduler.strategy
    logger.debug(f"Scheduler using '{strategy}' strategy")

    while True:
        async with session_factory() as session:
            job = await schedulers[strategy].get_next_job(session)

        if job is None:
            sleep_time = conf.scheduler.db_polling_interval_s
            logger.debug(f"No job to schedule, sleeping {sleep_time}")
            await asyncio.sleep(sleep_time)
            continue

        logger.info(f"Scheduling next job: {job.id}")

        queue = JobUpdateQueue(maxsize=QUEUE_MAXSIZE)
        # DB commit loop
        db_commit_task = asyncio.create_task(
            job_update_commiter(
                job_id=job.id, queue=queue, session_factory=session_factory
            ),
            name=f"Job {job.id} DB commit worker",
        )

        try:
            # QPU job execution
            worker_task = asyncio.create_task(
                qpu_worker.execute_job(
                    queue=queue,
                    nb_run=job.shots,
                    sequence=job.sequence,
                    backend_id=job.backend_id,
                    batch_id=job.session.slurm_job_id,
                ),
                name=f"Job {job.id} execution worker",
            )

            # Await end of job execution
            await worker_task
        finally:
            # Await that all updates are commited to DB. In a 'finally' because
            # a worker that raises, or a scheduler cancelled mid-job, otherwise
            # leaves its last update sitting in the queue forever - including
            # the backend_id that resuming a job relies on. Bounded so that an
            # unreachable DB cannot turn a SIGTERM into a hang.
            with suppress(TimeoutError):
                await asyncio.wait_for(queue.join(), timeout=DB_FLUSH_TIMEOUT_S)

            # Kill DB commit loop. In a 'finally' so that cancelling the
            # scheduler mid-job cannot leak a commiter that is inside an open
            # transaction, which would keep holding a write lock on the DB.
            db_commit_task.cancel()
            with suppress(asyncio.CancelledError):
                await db_commit_task

        async with session_factory() as session:
            stmt = select(Job.status).where(Job.id == job.id)
            status = (await session.execute(stmt)).scalar_one_or_none()
        logger.info(f"Job {job.id} ended with status: {status}")


async def run_cancellation_worker(engine: AsyncEngine, conf: Config):
    """Cancellation worker main logic

    Runs the cancellation worker in an infinite loop.
    Gets canceled by `main_async` when stop signal is received.
    """
    logger.info("Cancellation worker running.")

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    await cancellation_worker(conf=conf, session_factory=session_factory)


async def shutdown(engine: AsyncEngine):
    """Cleanup tasks and close DB connections."""

    logger.info("Closing database connections...")
    await engine.dispose()

    logger.info("Stopping all tasks")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        logger.debug("Stopping '%s'", task.get_name())
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)


async def main_async(conf: Config | None = None):
    """Main asyncio logic"""
    if conf is None:
        conf = Config()

    logging.config.dictConfig(config=conf.logging)
    engine = create_async_engine(build_db_url(conf.database), echo=conf.database.echo)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: stop_event.set())

    try:
        logger.info(
            "Starting scheduler and cancellation worker (Press Ctrl+C to exit)..."
        )

        # Start both scheduler and cancellation worker as separate tasks with same lifetime
        scheduler_task = loop.create_task(run_scheduler(engine, conf), name="Scheduler")
        cancellation_task = loop.create_task(
            run_cancellation_worker(engine, conf), name="Cancellation Worker"
        )

        # Wait for stop signal
        await stop_event.wait()

        # Cancel both tasks
        logger.info("Stopping scheduler and cancellation worker...")
        scheduler_task.cancel()
        cancellation_task.cancel()

        # Wait for graceful shutdown
        await asyncio.gather(scheduler_task, cancellation_task, return_exceptions=True)

    finally:
        await shutdown(engine)
        logger.info("Scheduler shutdown complete.")


def main():
    """Entrypoint"""
    asyncio.run(main_async())
