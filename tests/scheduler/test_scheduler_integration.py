"""Integration test"""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from warden.lib.config import Config, QPUConfig, SchedulerConfig
from warden.lib.models import Job, Session
from warden.scheduler.main import run_scheduler

BASE_URI_MOCK = "http://test:4300"
BASE_URI_MOCK_API = "http://test:4300/api/v1"
SLURM_USER_ID = "1234"


@pytest.fixture
def mock_api_client(mock_api_app):
    # The fastapi TestClient is based on the HTTPX client and should
    # have the same behavior/api as the sync HTTPX client
    # we can thus safely inject it into the test
    # https://fastapi.tiangolo.com/tutorial/testing/
    with TestClient(app=mock_api_app, base_url=BASE_URI_MOCK_API) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_scheduler_integration(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    mock_api_client: TestClient,
):
    """Test nominal behavior of scheduler with mock api

    Test rationale:
    - Create N_JOBS dummy jobs to run
    - Patch/inject httpx client with TestClient requesting
      directly to the ASGI FastAPI mock api
    - Run scheduler until:
        - All jobs have a "DONE" status in DB
        - Test timeout after TEST_TIMEOUT_S
    - Check n (jobs with status "DONE") = N_JOBS
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 10
    N_JOBS = 10

    conf = Config(
        scheduler=SchedulerConfig(
            strategy=strategy,
            db_polling_interval_s=0.01,
            qpu_polling_interval_s=0.01,
            qpu_polling_timeout_s=-1,
            job_polling_interval_s=0.01,
            job_polling_timeout_s=-1,
        ),
        qpu=QPUConfig(
            uri=BASE_URI_MOCK,
        ),
    )

    ##################
    ### TEST SETUP ###
    ##################

    jobs_to_run = [
        Job(
            id=i,
            sequence="{}",
            status="PENDING",
            shots=100,
            session=Session(slurm_job_id=1, user_id=SLURM_USER_ID),
        )
        for i in range(N_JOBS)
    ]

    async with db_session_maker() as session:
        session.add_all(jobs_to_run)
        await session.commit()

    stmt = select(func.count(Job.id)).where(Job.status == "DONE")

    async def wait_until_success(session: AsyncSession):
        while (await session.execute(stmt)).scalar() != N_JOBS:
            await asyncio.sleep(0.5)

    ##################
    ### TEST RUN   ###
    ##################

    # RUN SCHEDULER
    with patch("warden.lib.qpu_client.client.Client") as mock_client:
        # Injecting our FastAPI test client
        mock_client.return_value = mock_api_client
        main_task = asyncio.create_task(run_scheduler(db_engine, conf))

        async with db_session_maker() as session:
            try:
                async with asyncio.timeout(TEST_TIMEOUT_S):
                    await wait_until_success(session=session)
            finally:
                n_done = (await session.execute(stmt)).scalar()
                main_task.cancel()
                assert n_done == N_JOBS
