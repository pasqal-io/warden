"""Testing warden.scheduler.main.py"""

import asyncio
import math
import random
from datetime import datetime, timedelta

import pytest
import utils
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

    TEST_TIMEOUT_S = 3
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
            retry_max=10,
            retry_sleep_s=0,
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
        for _ in range(3):
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
            n_done = (await session.execute(stmt)).scalar()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_qpu_down(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
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

    TEST_TIMEOUT_S = 3
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
            retry_max=10,
            retry_sleep_s=0,
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
    await utils.create_n_jobs(db_session_maker, N_JOBS)

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
            utils.raise_main_scheduler_task_exception(main_task)
            n_done = (await session.execute(stmt)).scalar()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_job_timeout(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
):
    """Test scheduler behavior when jobs timeout

    Expected behavior: jobs that timeout are canceled on the QPU and
        return in "CANCELED" state.
    Except when we can't cancel the job because in this case the associated
        program has had time to finish. In which case it will return "DONE" state


    Test rationale:
    - Set job_polling_timout to a positive number to avoid
      infinite job status polling
    - Create N_JOBS dummy jobs to run
    - Select N_JOBS_TIMEOUT random job ID that will timeout
    - PasqOS API is mocked:
        - To return QPU status as "UP"
        - To accept job creation requests
        - To return "RUNNING" and then "DONE" status for each non-timeout job
        - For each ID in JOB_TIMEOUT_IDS:
            - Add N_JOB_POLLING_BEFORE_TIMEOUT "RUNNING" status return
            - Mock the job canceling API calls
                - Mock half the jobs not being cancelable because program is DONE
                - Other jobs return as CANCELED
    - Run scheduler until:
        - All jobs are either "DONE" or "CANCELED"
        - Test timout after TEST_TIMOUT_S
    - Check :
        - n(jobs "DONE") = N_JOBS - (N_JOBS_TIMEOUT // 2)
        - n(jobs "CANCELED") = (N_JOBS_TIMEOUT // 2)
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 3
    N_JOBS = 8
    N_JOBS_TIMEOUT = 4

    JOB_TIMEOUT_IDS = random.sample([i for i in range(N_JOBS - 1)], N_JOBS_TIMEOUT)

    # Do not set timeout time to a multiple of interval time
    # to have a deterministic number of polling requests
    # and not be impacted by micro-timing variation within the test
    JOB_POLLING_INTERVAL_S = 0.02
    JOB_POLLING_TIMEOUT_S = 0.05

    N_JOB_POLLING_BEFORE_TIMEOUT = (
        int(math.ceil(JOB_POLLING_TIMEOUT_S / JOB_POLLING_INTERVAL_S)) + 1
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
            retry_max=10,
            retry_sleep_s=0,
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
    job_timeout_counter = 0
    for job_uid in range(N_JOBS):
        return_create_json = {
            "data": {
                "uid": job_uid,
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
                "uid": job_uid,
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
                "uid": job_uid,
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
        # Check if job should timeout
        if job_uid in JOB_TIMEOUT_IDS:
            # Half the timeout jobs are actually done
            # before we try to cancel them
            is_cancelable = [True, False][job_timeout_counter % 2]
            job_timeout_counter += 1

            for _ in range(N_JOB_POLLING_BEFORE_TIMEOUT):
                httpx_mock.add_response(
                    method="GET",
                    status_code=200,
                    url=JOB_API + f"/{job_uid}",
                    json=return_running_json,
                )
            # Job cancellation requests
            return_cancelled_job_status = {
                "data": {
                    "uid": job_uid,
                    "batch_id": SLURM_USER_ID,
                    "status": "CANCELED",
                    "result": None,
                    # TODO: CHECK RETURN FIELDS HERE
                    "created_datetime": NOW.isoformat(),
                    "start_datetime": (NOW + timedelta(seconds=1)).isoformat(),
                    "end_datetime": None,
                }
            }
            return_cannot_cancel_program = {
                "code": "ABCD3003",
                "data": {
                    "description": "Cannot cancel program.",
                    # Program status
                    "status": "DONE",
                },
                "message": "Bad request.",
                "status": "fail",
            }
            if is_cancelable:
                # Job can be canceled
                httpx_mock.add_response(
                    method="PUT",
                    status_code=200,
                    url=JOB_API + f"/{job_uid}/cancel",
                    json=return_cancelled_job_status,
                )
            else:
                httpx_mock.add_response(
                    method="PUT",
                    status_code=400,
                    url=JOB_API + f"/{job_uid}/cancel",
                    json=return_cannot_cancel_program,
                )
                # Job can't be canceled
                # We just fetch the job status again
                httpx_mock.add_response(
                    method="GET",
                    status_code=200,
                    url=JOB_API + f"/{job_uid}",
                    json=return_done_json,
                )
        else:
            # Normal non-timeout job
            httpx_mock.add_response(
                method="GET",
                status_code=200,
                url=JOB_API + f"/{job_uid}",
                json=return_running_json,
            )
            httpx_mock.add_response(
                method="GET",
                status_code=200,
                url=JOB_API + f"/{job_uid}",
                json=return_done_json,
            )

    # Populate DB with jobs to run
    await utils.create_n_jobs(db_session_maker, N_JOBS)

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
            utils.raise_main_scheduler_task_exception(main_task)
            n_done = (await session.execute(stmt_done)).scalar()
            n_cancelled = (await session.execute(stmt_cancelled)).scalar()
            assert n_done == N_JOBS - (N_JOBS_TIMEOUT // 2)
            assert n_cancelled == (N_JOBS_TIMEOUT // 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_retry_transient_errors(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
):
    """Test that the scheduler is able to process
    a list of jobs when the QPU is up and running
    while handling various network and apllication
    transient errors

    Test rationale:
    - Create N_JOBS dummy jobs to run
    - PasqOS API is mocked:
        - For each requests to return a list of RETRYABLE transient errors
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

    TEST_TIMEOUT_S = 3
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
        # Setting retr_sleep_s to 0 to speed up testing
        # max_try arbitrarily set to 10, must be more than the number of errors
        # the helper function '_add_transient_errors' adds
        qpu=QPUConfig(
            uri=QPU_URI, retry_max=10, retry_sleep_s=0
        ),  # <----- IMPORTANT TO THIS TEST
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
            n_done = (await session.execute(stmt)).scalar()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_pasqos_api_unreachable(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
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

    TEST_TIMEOUT_S = 3
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
        qpu=QPUConfig(uri=QPU_URI, retry_max=10, retry_sleep_s=0),
    )

    ##################
    ### TEST SETUP ###
    ##################

    # Mock API down
    httpx_mock.add_exception(ConnectError("Connection refused"), is_reusable=True)

    # Populate DB with jobs to run
    await utils.create_n_jobs(db_session_maker, N_JOBS)

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
            utils.raise_main_scheduler_task_exception(main_task)
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
):
    """Test scheduler behavior when PasqOS API fails to create a job

    Expected behavior is that all jobs return as ERROR after the
    request fails after retries.

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

    TEST_TIMEOUT_S = 3
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
        qpu=QPUConfig(uri=QPU_URI, retry_max=10, retry_sleep_s=0),
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
    httpx_mock.add_response(
        status_code=500,
        url=JOB_API,
        method="POST",
        is_reusable=True,
    )

    # Populate DB with jobs to run
    await utils.create_n_jobs(db_session_maker, N_JOBS)

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
            utils.raise_main_scheduler_task_exception(main_task)
            n_done = (await session.execute(stmt)).scalar()
            assert n_done == N_JOBS


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["FIFO"])
async def test_run_main_scheduler_job_client_error_timeout(
    strategy: str,
    db_engine: AsyncEngine,
    db_session_maker: async_sessionmaker,
    httpx_mock: HTTPXMock,
):
    """Test scheduler behavior when job timesout due to the requests
    to get the job status failing

    Expected behavior is that all jobs return with an ERROR status

    Test rationale:
    - Configure job timout to non-negative value to avoid
      infinite polling
    - Create N_JOBS dummy jobs to run
    - PasqOS API is mocked:
        - To return QPU status as "UP"
        - To accept job creation request
        - To return 500 errors when polling job status
        - To return 500 errors when trying to cancel job
          (it's the same backend request in PasqOS)
    - Run scheduler until:
        - All jobs have an "ERROR" status is DB
        - Test timeout after TEST_TIMEOUT_S
    - Check n (jobs with status "ERROR") = N_JOBS
    """

    ##################
    ### TEST CONF  ###
    ##################

    TEST_TIMEOUT_S = 3
    N_JOBS = 1
    EXPECTED_STATUS = "ERROR"

    conf = Config(
        scheduler=SchedulerConfig(
            strategy=strategy,
            db_polling_interval_s=0.01,
            qpu_polling_interval_s=0.01,
            qpu_polling_timeout_s=-1,
            # Set job_polling_timeout_s to a non-negative value to
            # avoid infinite job status polling
            job_polling_interval_s=0.05,
            job_polling_timeout_s=0.5,  # <----- IMPORTANT TO THIS TEST
        ),
        qpu=QPUConfig(
            uri=QPU_URI,
            retry_max=10,
            retry_sleep_s=0,
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
        # Unable to poll job status
        httpx_mock.add_response(
            method="GET", url=JOB_API + f"/{id}", status_code=500, is_reusable=True
        )
        # Job cancellation requests
        # Unable to cancel job
        httpx_mock.add_response(
            method="PUT",
            url=JOB_API + f"/{id}/cancel",
            status_code=500,
            is_reusable=True,
        )

    # Populate DB with jobs to run
    await utils.create_n_jobs(db_session_maker, N_JOBS)

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
            utils.raise_main_scheduler_task_exception(main_task)
            n_done = (await session.execute(stmt)).scalar()
            assert n_done == N_JOBS
