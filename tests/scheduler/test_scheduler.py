"""Testing warden.scheduler.main.py"""

import asyncio
import math
import random
from datetime import datetime, timedelta

import pytest
from httpx import ConnectError, NetworkError, TimeoutException
from pytest_httpx import HTTPXMock
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from warden.lib.config import Config, QPUConfig, SchedulerConfig
from warden.lib.models import Job
from warden.scheduler.main import run_scheduler

NOW = datetime.now()

SLURM_USER_ID = "1234"

QPU_PROGRAM_UID = 0

QPU_URI = "http://test_api:4300"
API_VERSION = "v1"
API_URI = f"{QPU_URI}/api/{API_VERSION}"

SYSTEM_OPERATIONAL_API = API_URI + "/system/operational"
JOB_API = API_URI + "/jobs"
SYSTEM_API = API_URI + "/system"
PROGRAM_API = API_URI + "/programs"


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
    helpers,
):
    """Test that the scheduler is able to process
    a list of jobs when the QPU is up and running

    Test rationale:
    - Create N_JOBS dummy jobs to run
    - PasqOS API is mocked:
        - To return QPU status as "UP"
        - To accept job creation requests
        - To return "RUNNING" and then "DONE" status for each job
    - Run scheduler until:
        - All jobs have a "DONE" status is DB
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
            uri=QPU_URI,
        ),
    )

    ##################
    ### TEST SETUP ###
    ##################

    # QPU status
    httpx_mock.add_response(
        method="GET",
        url=SYSTEM_OPERATIONAL_API,
        json={"data": {"operational_status": "UP"}},
        is_reusable=True,
    )
    for id in range(N_JOBS):
        return_create_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "PENDING",
                "result": None,
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": None,
                "end_datetime": None,
            }
        }
        # Create Job
        httpx_mock.add_response(
            method="POST", status_code=200, url=JOB_API, json=return_create_json
        )
        return_running_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "RUNNING",
                "result": None,
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
                "end_datetime": None,
            }
        }
        return_done_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "DONE",
                "result": '[{"counters": ["0001": 1, "0010": 2, "0100": 3, "1000": 4]}]',
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
                "end_datetime": (NOW + timedelta(seconds=2)).isoformat(),
            }
        }
        # Job running
        httpx_mock.add_response(
            method="GET",
            status_code=200,
            url=JOB_API + f"/{id}",
            json=return_running_json,
        )
        # Job done
        httpx_mock.add_response(
            method="GET", status_code=200, url=JOB_API + f"/{id}", json=return_done_json
        )

    # Populate DB with jobs to run
    await helpers.create_n_jobs(db_session_maker, N_JOBS)

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
            n_done = (await session.execute(stmt)).scalar()
            main_task.cancel()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_qpu_down(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
    helpers,
):
    """Test that the scheduler sets jobs to ERROR
    when the QPU is not responsive for a while

    Test rationale:
    - Set qpu_polling_timeout_s to a positive time
    - Create N_JOBS dummy jobs to run
    - PasqOS API is mocked:
        - To always return QPU status as "DOWN"
        - No need to mock jobs calls
    - Run scheduler until:
        - All jobs have an "ERROR" status
        - Test timeout after TEST_TIMEOUT_S
    - Check n (jobs with status "ERROR") = N_JOBS
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 10
    N_JOBS = 3

    EXPECTED_STATUS = "ERROR"

    conf = Config(
        scheduler=SchedulerConfig(
            strategy=strategy,
            db_polling_interval_s=0.01,
            # Set QPU timeout to non-negative value to
            # avoid infinite polling of QPU status
            qpu_polling_interval_s=0.01,  # <----- IMPORTANT TO THIS TEST
            qpu_polling_timeout_s=0.03,  # <----- IMPORTANT TO THIS TEST
            job_polling_interval_s=0.01,
            job_polling_timeout_s=-1,
        ),
        qpu=QPUConfig(
            uri=QPU_URI,
        ),
    )

    ##################
    ### TEST SETUP ###
    ##################

    httpx_mock.add_response(
        method="GET",
        status_code=200,
        url=SYSTEM_OPERATIONAL_API,
        json={"data": {"operational_status": "DOWN"}},
        is_reusable=True,
    )

    # Populate DB with jobs to run
    await helpers.create_n_jobs(db_session_maker, N_JOBS)

    stmt = select(func.count(Job.id)).where(Job.status == EXPECTED_STATUS)

    async def wait_until_error(session: AsyncSession):
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
                await wait_until_error(session=session)
        finally:
            n_done = (await session.execute(stmt)).scalar()
            main_task.cancel()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_job_timeout(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
    helpers,
):
    """Thest scheduler behavior when one
    scheduled jobs timesout

    Test rationale:
    - Set job_polling_timout to a positive number to avoid
      infinite job status polling
    - Create N_JOBS dummy jobs to run
    - Select one random JOB_TIMEOUT_ID job ID that will timeout
    - PasqOS API is mocked:
        - To return QPU status as "UP"
        - To accept job creation requests
        - To return "RUNNING" and then "DONE" status for each job
        - For JOB_TIMEOUT_ID:
            - Add N_JOB_POLLING_BEFORE_TIMEOUT "RUNNING" status return
            - Mock the job canceling API calls
    - Run scheduler until:
        - All jobs are either "DONE" or "CANCELED"
        - Test timout after TEST_TIMOUT_S
    - Check :
        - n(jobs "DONE") = N_JOBS - 1
        - n(jobs "CANCELED") = 1
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 10
    N_JOBS = 5

    JOB_TIMEOUT_ID = random.randint(0, N_JOBS - 1)

    # Do not set timeout time to a multiple of interval time
    # to have a deterministic number of polling requests
    # and not be impacted by micro-timing variation within the test
    JOB_POLLING_INTERVAL_S = 0.02
    JOB_POLLING_TIMEOUT_S = 0.05

    N_JOB_POLLING_BEFORE_TIMEOUT = int(
        math.ceil(JOB_POLLING_TIMEOUT_S / JOB_POLLING_INTERVAL_S)
    )

    conf = Config(
        scheduler=SchedulerConfig(
            strategy=strategy,
            db_polling_interval_s=0.01,
            qpu_polling_interval_s=0.01,
            qpu_polling_timeout_s=-1,
            # Set job_polling_timeout_s to a non-negative value to
            # avoid infinite job status polling
            job_polling_interval_s=JOB_POLLING_INTERVAL_S,  # <----- IMPORTANT TO THIS TEST
            job_polling_timeout_s=JOB_POLLING_TIMEOUT_S,  # <----- IMPORTANT TO THIS TEST
        ),
        qpu=QPUConfig(
            uri=QPU_URI,
        ),
    )

    ##################
    ### TEST SETUP ###
    ##################

    # QPU status
    httpx_mock.add_response(
        method="GET",
        url=SYSTEM_OPERATIONAL_API,
        json={"data": {"operational_status": "UP"}},
        is_reusable=True,
    )

    # JOB creation and polling
    for id in range(N_JOBS):
        return_create_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "PENDING",
                "result": None,
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": None,
                "end_datetime": None,
            }
        }
        return_running_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "RUNNING",
                "result": None,
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
                "end_datetime": None,
            }
        }
        return_done_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "DONE",
                "result": '[{"counters": ["0001": 1, "0010": 2, "0100": 3, "1000": 4]}]',
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
                "end_datetime": (NOW + timedelta(seconds=2)).isoformat(),
            }
        }
        # JOB creation
        httpx_mock.add_response(
            method="POST", status_code=200, url=JOB_API, json=return_create_json
        )
        # JOB polling
        if id == JOB_TIMEOUT_ID:
            for _ in range(N_JOB_POLLING_BEFORE_TIMEOUT):
                httpx_mock.add_response(
                    method="GET",
                    status_code=200,
                    url=JOB_API + f"/{id}",
                    json=return_running_json,
                )
        else:
            httpx_mock.add_response(
                method="GET",
                status_code=200,
                url=JOB_API + f"/{id}",
                json=return_running_json,
            )
            httpx_mock.add_response(
                method="GET",
                status_code=200,
                url=JOB_API + f"/{id}",
                json=return_done_json,
            )

    # Job cancellation requests
    return_cancelled_job_program = {
        "data": {
            "uid": QPU_PROGRAM_UID,
            "status": "RUNNING",
            # ...
        }
    }
    httpx_mock.add_response(
        method="GET",
        status_code=200,
        url=PROGRAM_API + f"/{QPU_PROGRAM_UID}",
        json=return_cancelled_job_program,
    )
    return_cancelled_job_status = {
        "data": {
            "uid": JOB_TIMEOUT_ID,
            "batch_id": SLURM_USER_ID,
            "status": "CANCELED",
            "result": None,
            # TODO: CHECK RETURN FIELDS HERE
            "created_datetime": NOW.isoformat(),
            "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
            "end_datetime": None,
        }
    }
    httpx_mock.add_response(
        method="PUT",
        status_code=200,
        url=JOB_API + f"/{JOB_TIMEOUT_ID}/cancel",
        json=return_cancelled_job_status,
    )
    # TODO REMOVE ?
    httpx_mock.add_response(
        method="GET",
        status_code=200,
        url=JOB_API + f"/{JOB_TIMEOUT_ID}",
        json=return_cancelled_job_status,
    )

    # Populate DB with jobs to run
    await helpers.create_n_jobs(db_session_maker, N_JOBS)

    stmt_done = select(func.count(Job.id)).where(Job.status == "DONE")
    stmt_cancelled = select(func.count(Job.id)).where(Job.status == "CANCELED")
    stmt_processed = select(func.count(Job.id)).where(
        Job.status.in_(["DONE", "CANCELED"])
    )

    ##################
    ### TEST RUN   ###
    ##################

    async def wait_until_success(session: AsyncSession):
        while (await session.execute(stmt_processed)).scalar() != N_JOBS:
            await asyncio.sleep(0.5)

    # RUN SCHEDULER
    main_task = asyncio.create_task(run_scheduler(db_engine, conf))

    async with db_session_maker() as session:
        try:
            async with asyncio.timeout(TEST_TIMEOUT_S):
                await wait_until_success(session=session)
        finally:
            n_done = (await session.execute(stmt_done)).scalar()
            n_cancelled = (await session.execute(stmt_cancelled)).scalar()
            main_task.cancel()
            assert n_done == N_JOBS - 1
            assert n_cancelled == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_transient_errors(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
    helpers,
):
    """Test that the scheduler is able to process
    a list of jobs when the QPU is up and running
    while handling various network and apllication
    transient errors

    Test rationale:
    - Create N_JOBS dummy jobs to run
    - PasqOS API is mocked:
        - For each requests to return a list of transient errors
          before returning the actual response
        - To return QPU status as "UP"
        - To accept job creation requests
        - To return "RUNNING" and then "DONE" status for each job
    - Run scheduler until:
        - All jobs have a "DONE" status is DB
        - Test timeout after TEST_TIMEOUT_S
    - Check n (jobs with status "DONE") = N_JOBS
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 10
    N_JOBS = 1

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
            uri=QPU_URI,
        ),
    )

    ##################
    ### TEST SETUP ###
    ##################

    def _add_transient_errors(httpx_mock: HTTPXMock, url: str, method: str):
        httpx_mock.add_response(url=url, method=method, status_code=500)
        httpx_mock.add_response(url=url, method=method, status_code=502)
        httpx_mock.add_response(url=url, method=method, status_code=503)
        httpx_mock.add_response(url=url, method=method, status_code=504)
        httpx_mock.add_response(url=url, method=method, status_code=429)
        httpx_mock.add_exception(
            TimeoutException("Server took too long"), url=url, method=method
        )
        httpx_mock.add_exception(NetworkError("Network error"), url=url, method=method)

    # QPU status
    _add_transient_errors(httpx_mock, SYSTEM_OPERATIONAL_API, "GET")
    httpx_mock.add_response(
        method="GET",
        url=SYSTEM_OPERATIONAL_API,
        json={"data": {"operational_status": "UP"}},
        is_reusable=True,
    )
    for id in range(N_JOBS):
        return_create_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "PENDING",
                "result": None,
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": None,
                "end_datetime": None,
            }
        }
        # Create Job
        _add_transient_errors(httpx_mock, JOB_API, "POST")
        httpx_mock.add_response(
            method="POST", status_code=200, url=JOB_API, json=return_create_json
        )
        return_running_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "RUNNING",
                "result": None,
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
                "end_datetime": None,
            }
        }
        return_done_json = {
            "data": {
                "uid": id,
                "batch_id": SLURM_USER_ID,
                "status": "DONE",
                "result": '[{"counters": ["0001": 1, "0010": 2, "0100": 3, "1000": 4]}]',
                "program_id": QPU_PROGRAM_UID,
                "created_datetime": NOW.isoformat(),
                "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
                "end_datetime": (NOW + timedelta(seconds=2)).isoformat(),
            }
        }
        # Job running
        local_job_id_url = JOB_API + f"/{id}"
        _add_transient_errors(httpx_mock, local_job_id_url, "GET")
        httpx_mock.add_response(
            method="GET",
            status_code=200,
            url=local_job_id_url,
            json=return_running_json,
        )
        # Job done
        _add_transient_errors(httpx_mock, local_job_id_url, "GET")
        httpx_mock.add_response(
            method="GET", status_code=200, url=local_job_id_url, json=return_done_json
        )

    # Populate DB with jobs to run
    await helpers.create_n_jobs(db_session_maker, N_JOBS)

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
            n_done = (await session.execute(stmt)).scalar()
            main_task.cancel()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_pasqos_api_unreachable(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
    helpers,
):
    """Test scheduler behavior when PasqOS API is unreachable.
    Expected behavior is that all jobs are set to "ERROR" status
    after retries fail.



    Test rationale:
    - Create a dummy jobs to run
    - PasqOS API is mocked:
        - To return QPU status as "Down"
    - Run scheduler until:
        - All jobs have a "ERROR" status is DB
        - Test timeout after TEST_TIMEOUT_S
    - Check n (jobs with status "ERROR") = N_JOBS
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 10
    N_JOBS = 1
    EXPECTED_STATUS = "ERROR"

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
            uri=QPU_URI,
        ),
    )

    ##################
    ### TEST SETUP ###
    ##################

    # Mock API down
    httpx_mock.add_exception(ConnectError("Connection refused"), is_reusable=True)

    # Populate DB with jobs to run
    await helpers.create_n_jobs(db_session_maker, N_JOBS)

    stmt = select(func.count(Job.id)).where(Job.status == EXPECTED_STATUS)

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
            n_done = (await session.execute(stmt)).scalar()
            main_task.cancel()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_job_creation_client_error(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
    helpers,
):
    """Test scheduler behavior when PasqOS API is unreachable.
    Expected behavior is that all jobs are set to "ERROR" status
    after retries fail.

    Test rationale:
    - Create N_JOBS dummy jobs to run
    - PasqOS API is mocked:
        - To return QPU status as "UP"
        - Return exceptions when attempting to create a job
    - Run scheduler until:
        - All jobs have a "ERROR" status is DB
        - Test timeout after TEST_TIMEOUT_S
    - Check n (jobs with status "ERROR") = N_JOBS
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 10
    N_JOBS = 3
    EXPECTED_STATUS = "ERROR"

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
            uri=QPU_URI,
        ),
    )

    ##################
    ### TEST SETUP ###
    ##################

    # Mock QPU status
    httpx_mock.add_response(
        method="GET",
        url=SYSTEM_OPERATIONAL_API,
        json={"data": {"operational_status": "UP"}},
        is_reusable=True,
    )

    # Mock job creation error
    httpx_mock.add_exception(
        exception=ConnectError("Connection refused"),
        url=JOB_API,
        method="POST",
        is_reusable=True,
    )

    # Populate DB with jobs to run
    await helpers.create_n_jobs(db_session_maker, N_JOBS)

    stmt = select(func.count(Job.id)).where(Job.status == EXPECTED_STATUS)

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
            n_done = (await session.execute(stmt)).scalar()
            main_task.cancel()
            assert n_done == N_JOBS
