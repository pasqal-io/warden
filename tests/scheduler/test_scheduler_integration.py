"""Integration test"""

import asyncio
import logging

import pytest
import utils
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.mock_qpu_api.samples import FAKE_RESULTS
from warden.lib.config import Config, QPUConfig, SchedulerConfig
from warden.lib.models import Job
from warden.scheduler.main import run_scheduler

BASE_URI_MOCK = "http://test:4300"


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_scheduler_integration(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    mock_qpu_api_app: FastAPI,
    caplog,
):
    """Test nominal behavior of scheduler with mock qpu api

    Test rationale:
    - Inject httpx client through the config with
      a FastAPI TestClient requesting directly to the ASGI 'mock_qpu_api' app
    - Create N_JOBS dummy jobs to run
    - Run scheduler until:
        - All jobs have a "DONE" status in DB
        - Test timeout after TEST_TIMEOUT_S
    - Check n (jobs with status "DONE") = N_JOBS
    """

    ##################
    ### TEST CONF  ###
    ##################

    # Enable warden logging for jobs 'logs' field to be populated
    caplog.set_level(logging.INFO, logger="warden")

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
        qpu=QPUConfig(uri=BASE_URI_MOCK, retry_max=10, retry_sleep_s=0),
    )

    #################################
    # Injecting FastAPI ASGI client #
    #################################
    conf.qpu._client = TestClient(app=mock_qpu_api_app)
    #################################

    ##################
    ### TEST SETUP ###
    ##################

    await utils.create_n_jobs(db_session_maker, N_JOBS)

    stmt = select(func.count(Job.id)).where(Job.status == "DONE")

    async def wait_until_success(session: AsyncSession):
        while (await session.execute(stmt)).scalar() != N_JOBS:
            await asyncio.sleep(0.5)

    ##################
    ### TEST RUN   ###
    ##################

    # RUN SCHEDULER
    main_task = asyncio.create_task(run_scheduler(db_engine, conf))

    async with db_session_maker() as session:
        try:
            async with asyncio.timeout(TEST_TIMEOUT_S):
                await wait_until_success(session=session)
        finally:
            utils.raise_main_scheduler_task_exception(main_task)

            stmt_all = select(Job).where(Job.status == "DONE")
            jobs_done = (await session.execute(stmt_all)).scalars().all()
            assert len(jobs_done) == N_JOBS
            for job in jobs_done:
                assert job.results == FAKE_RESULTS
                assert job.logs != ""
                assert "done" in job.logs
