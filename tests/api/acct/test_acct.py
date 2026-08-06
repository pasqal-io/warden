###############################################################################
############################ /accounting ROUTE TESTS ##########################
###############################################################################


from datetime import timedelta
from typing import Literal

import pytest

from tests.api.acct.conftest import ACCT_ENDPOINT, acct_populate_db
from tests.api.conftest import mock_munge_auth


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_ENDPOINT,))
async def test_acct_nominal(client, app, endpoint: Literal["/accounting"]):
    """Assert that /accounting lists one row per user with its session and
    job summaries (counts and durations) correctly aggregated."""
    N_USERS = 3
    JOB_STATUSES = ("DONE", "ERROR")
    SESSION_DURATION = timedelta(minutes=30)
    JOB_WAIT = timedelta(seconds=15)
    JOB_EXECUTION = timedelta(seconds=45)
    JOB_SHOTS = 100

    # 2 jobs per user/session, one DONE and one ERROR
    user_uids, _, _ = await acct_populate_db(
        app,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        job_statuses=JOB_STATUSES,
        job_wait_time=JOB_WAIT,
        job_execution_time=JOB_EXECUTION,
        job_shots=JOB_SHOTS,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(endpoint + "?limit=100")
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == N_USERS
    assert len(body["data"]) == N_USERS

    expected_session_duration = int(SESSION_DURATION.total_seconds())
    expected_wait_time = int(JOB_WAIT.total_seconds())
    expected_execution_time = int(JOB_EXECUTION.total_seconds())
    # One job per status, so per-user totals are the per-job time times the
    # number of statuses.
    expected_jobs_execution_time = expected_execution_time * len(JOB_STATUSES)
    expected_jobs_wait_time = expected_wait_time * len(JOB_STATUSES)

    for i, user_data in enumerate(body["data"]):
        assert user_data["user_id"] == user_uids[i]
        assert user_data["sessions"]["count"] == 1
        assert user_data["sessions"]["total_duration"] == expected_session_duration
        assert user_data["jobs"]["count"] == len(JOB_STATUSES)
        assert user_data["jobs"]["execution_time"] == expected_jobs_execution_time
        assert user_data["jobs"]["wait_time"] == expected_jobs_wait_time
        assert user_data["jobs"]["shots"] == JOB_SHOTS * len(JOB_STATUSES)
        assert {stat["status"] for stat in user_data["jobs"]["stats"]} == set(
            JOB_STATUSES
        )
        for stat in user_data["jobs"]["stats"]:
            assert stat["count"] == 1
            assert stat["execution_time"] == expected_execution_time
            assert stat["wait_time"] == expected_wait_time
            assert stat["shots"] == JOB_SHOTS


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_ENDPOINT,))
async def test_acct_session_without_jobs(client, app, endpoint: Literal["/accounting"]):
    """Assert that a session with no job is still reported, with an empty
    job summary rather than a missing/erroring row."""
    N_USERS = 2
    SESSION_DURATION = timedelta(minutes=30)

    user_uids, _, _ = await acct_populate_db(
        app,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        job_statuses=(),
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(endpoint + "?limit=100")
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == N_USERS
    assert len(body["data"]) == N_USERS

    expected_session_duration = int(SESSION_DURATION.total_seconds())
    for i, user_data in enumerate(body["data"]):
        assert user_data["user_id"] == user_uids[i]
        assert user_data["sessions"]["count"] == 1
        assert user_data["sessions"]["total_duration"] == expected_session_duration
        assert user_data["jobs"]["count"] == 0
        assert user_data["jobs"]["execution_time"] == 0
        assert user_data["jobs"]["wait_time"] == 0
        assert user_data["jobs"]["stats"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_ENDPOINT,))
async def test_acct_reported_durations(client, app, endpoint: Literal["/accounting"]):
    """Assert that reported session and job durations are the real elapsed seconds."""
    N_USERS = 3
    SESSION_DURATION = timedelta(seconds=60)

    JOB_WAIT = timedelta(seconds=15)
    JOB_EXECUTION = timedelta(seconds=45)
    await acct_populate_db(
        app,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        job_wait_time=JOB_WAIT,
        job_execution_time=JOB_EXECUTION,
    )

    SESSION_DURATION = int(SESSION_DURATION.total_seconds())
    JOB_WAIT_TIME = int(JOB_WAIT.total_seconds())
    JOB_EXECUTION_TIME = int(JOB_EXECUTION.total_seconds())

    with mock_munge_auth(app, uid=0):
        response = await client.get(endpoint + "?limit=100")
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == N_USERS

    for user_data in data:
        # One session of SESSION_DURATION per user.
        assert user_data["sessions"]["count"] == 1
        assert user_data["sessions"]["total_duration"] == SESSION_DURATION

        # One job, spanning the whole session.
        assert user_data["jobs"]["count"] == 1
        assert len(user_data["jobs"]["stats"]) == 1
        assert user_data["jobs"]["stats"][0]["execution_time"] == JOB_EXECUTION_TIME
        assert user_data["jobs"]["stats"][0]["wait_time"] == JOB_WAIT_TIME
