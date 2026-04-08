"""Test helper functions"""

from asyncio import Task

from sqlalchemy.ext.asyncio import async_sessionmaker

from warden.lib.models import Job, Session


async def create_n_jobs(db_session_maker: async_sessionmaker, n_jobs: int):
    """Creates n_jobs mock jobs to run in the warden db"""
    SLURM_USER_ID = "1234"

    jobs_to_run = [
        Job(
            id=i,
            sequence="{}",
            status="PENDING",
            shots=100,
            session=Session(slurm_job_id=1, user_id=SLURM_USER_ID),
        )
        for i in range(n_jobs)
    ]

    async with db_session_maker() as session:
        session.add_all(jobs_to_run)
        await session.commit()


@staticmethod
def raise_main_scheduler_task_exception(scheduler_task: Task) -> None:
    """
    The main scheduler task is an infinite loop that we don't await.
    In case it encounters an unhandled exception during the test,
    the test will just timeout and the exceptions encountered in
    the main scheduler task will not be raised and will make debugging
    the tests much more difficult.

    This helper function is here to make sure that
    IF the scheduler task encounters an exception, we raise it again to
    make it visible to the developer.
    """
    if scheduler_task.done() and scheduler_task.exception():
        raise scheduler_task.exception()
    else:
        scheduler_task.cancel()
