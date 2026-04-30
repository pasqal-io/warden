"""Main logic of the scheduler"""

import asyncio
import logging.config
import signal
from asyncio import Queue

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from warden.lib.config import Config
from warden.lib.db.database import build_db_url
from warden.lib.models import Job
from warden.scheduler.strategy import schedulers
from warden.scheduler.types import JobUpdate
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

        queue: Queue[JobUpdate] = Queue(maxsize=QUEUE_MAXSIZE)
        # DB commit loop
        db_commit_task = asyncio.create_task(
            async_commit(job_id=job.id, queue=queue, session_factory=session_factory)
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

        async with session_factory() as session:
            stmt = select(Job.status).where(Job.id == job.id)
            status = (await session.execute(stmt)).scalar_one_or_none()
        logger.info(f"Job {job.id} ended with status: {status}")


async def async_commit(
    job_id: int, queue: Queue, session_factory: async_sessionmaker[AsyncSession]
):
    """Async coroutine loop to continuously Job info during execution"""
    while True:
        job_update: JobUpdate = await queue.get()

        async with session_factory() as session:
            try:
                async with session.begin():
                    session.begin()
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
                                "logs": case(
                                    (
                                        func.coalesce(Job.logs, "") == "",
                                        job_update.new_logs,
                                    ),
                                    else_=Job.logs + job_update.new_logs,
                                ),
                            }
                        )
                    )
                    await session.execute(stmt)
                logger.debug(f"Job {job_id} updated in db")
            except Exception as e:
                logger.error(f"DB Update failed: {e}")
            finally:
                queue.task_done()


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
    engine = create_async_engine(build_db_url(conf.database), echo=conf.database.echo)
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
