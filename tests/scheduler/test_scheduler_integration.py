"""Integration test"""

import asyncio
import logging
from datetime import datetime

import pytest
import utils
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.mock_qpu_api.config import TimedConfig
from tests.mock_qpu_api.samples import FAKE_RESULTS
from warden.lib.config import Config, QPUConfig, SchedulerConfig, SchedulerStrategy
from warden.lib.models import Job, Session
from warden.scheduler.main import run_cancellation_worker, run_scheduler

BASE_URI_MOCK = "http://test:4300"


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", list(SchedulerStrategy))
async def test_run_scheduler_integration(
    strategy: SchedulerStrategy,
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
            job_polling_interval_s=0.01,
        ),
        qpu=QPUConfig(uri=BASE_URI_MOCK, retry_sleep_s=0),
    )

    #################################
    # Injecting FastAPI ASGI client #
    #################################
    app = mock_qpu_api_app
    # No need for timing of job execution in this test
    app.state.timed_config = TimedConfig(shot_duration_s=0)
    conf.qpu._client = TestClient(app)
    #################################

    ##################
    ### TEST SETUP ###
    ##################

    await utils.create_n_jobs(db_session_maker, N_JOBS)

    # The terminal status is committed before the closing "Job execution ended
    # with status 'DONE'" log line is flushed, so waiting on the status alone
    # races with the log assertions below. Wait for the logs too.
    stmt = select(func.count(Job.id)).where(
        Job.status == "DONE", Job.logs.contains("DONE")
    )

    ##################
    ### TEST RUN   ###
    ##################

    # RUN SCHEDULER
    main_task = asyncio.create_task(run_scheduler(db_engine, conf))

    async with db_session_maker() as session:
        try:
            async with asyncio.timeout(TEST_TIMEOUT_S):
                await utils.wait_until_scalar_equals(
                    session, stmt, N_JOBS, interval=0.5
                )
        finally:
            utils.raise_task_exception(main_task)

            stmt_all = select(Job).where(Job.status == "DONE")
            jobs_done = (await session.execute(stmt_all)).scalars().all()
            assert len(jobs_done) == N_JOBS
            for job in jobs_done:
                assert job.results == FAKE_RESULTS
                assert job.logs != ""
                assert "DONE" in job.logs


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", list(SchedulerStrategy))
async def test_run_scheduler_integration_cancellation_worker(
    strategy: SchedulerStrategy,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    mock_qpu_api_app: FastAPI,
    caplog,
):
    """Test behavior of scheduler with mock qpu api when jobs are requested to be deleted

    Test rationale:
    - Inject httpx client through the config with
      a FastAPI TestClient requesting directly to the ASGI 'mock_qpu_api' app
        - The 'mock_qpu_api' is set to simulate job execution with a fixed duration
    - Create N_JOBS dummy job to run
        - One of them is tagged to be canceled with `canceled_at` timestamp
    - Start the scheduler
    - Start the cancellation worker
    - Update the job in DB with a `canceled_at` timestamp to
    - Run scheduler until N_JOBS are either "DONE" or "CANCELED"
    - Check n (jobs with status "CANCELED") = 1
        - It has the right id that we requested to be canceled
    - Check n (jobs with status "DONE") = N_JOBS-1
    """

    ##################
    ### TEST CONF  ###
    ##################

    # Enable warden logging for jobs 'logs' field to be populated
    caplog.set_level(logging.INFO, logger="warden")

    TEST_TIMEOUT_S = 10
    N_JOBS = 5
    N_SHOTS = 500

    conf = Config(
        scheduler=SchedulerConfig(
            strategy=strategy,
            db_polling_interval_s=0.1,
            qpu_polling_interval_s=0.1,
            job_polling_interval_s=0.1,
        ),
        qpu=QPUConfig(uri=BASE_URI_MOCK, retry_sleep_s=0),
    )

    #################################
    # Injecting FastAPI ASGI client #
    #################################
    app = mock_qpu_api_app
    # Simulate job execution timing so that
    # the cancellation worker has time to observe and cancel jobs
    app.state.timed_config = TimedConfig(shot_duration_s=0.001)
    # Each job with 500 shots is expected to take 0.5 seconds to complete
    conf.qpu._client = TestClient(app)
    #################################

    ##################
    ### TEST SETUP ###
    ##################

    await utils.create_n_jobs(db_session_maker, N_JOBS - 1, N_SHOTS)

    job_to_cancel = Job(
        sequence="{}",
        status="PENDING",
        shots=N_SHOTS,
        session=Session(slurm_job_id="1", user_id="1234"),
        canceled_at=datetime.now(),
    )

    async with db_session_maker() as session:
        session.add(job_to_cancel)
        await session.commit()
        await session.refresh(job_to_cancel)

    JOB_TO_CANCEL_ID = job_to_cancel.id

    # Same race as above: wait for the closing log line, not just the status
    stmt = select(func.count(Job.id)).where(
        Job.status.in_(("CANCELED", "DONE")),
        Job.logs.contains("Job execution ended"),
    )

    ##################
    ### TEST RUN   ###
    ##################

    # RUN SCHEDULER
    main_task = asyncio.create_task(run_scheduler(db_engine, conf))
    # RUN CANCELLATION WORKER
    cancellation_worker_task = asyncio.create_task(
        run_cancellation_worker(db_engine, conf)
    )

    async with db_session_maker() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_to_cancel.id)
            .values({"canceled_at": datetime.now()})
        )
        await session.commit()

    async with db_session_maker() as session:
        try:
            async with asyncio.timeout(TEST_TIMEOUT_S):
                await utils.wait_until_scalar_equals(
                    session, stmt, N_JOBS, interval=0.5
                )
        finally:
            utils.raise_task_exception(main_task)
            utils.raise_task_exception(cancellation_worker_task)

            stmt_done = select(Job).where(Job.status == "CANCELED")
            jobs_done = (await session.execute(stmt_done)).scalars().all()
            assert len(jobs_done) == 1
            for job in jobs_done:
                assert job.id == JOB_TO_CANCEL_ID
                assert job.logs != ""
                assert "CANCELED" in job.logs

            stmt_done = select(Job).where(Job.status == "DONE")
            jobs_done = (await session.execute(stmt_done)).scalars().all()
            assert len(jobs_done) == N_JOBS - 1
            for job in jobs_done:
                assert job.logs != ""
                assert "CANCELED" not in job.logs
