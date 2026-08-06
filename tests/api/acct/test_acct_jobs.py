from datetime import timedelta

import pytest

from tests.api.acct.conftest import ACCT_JOBS_ENDPOINT, acct_populate_db
from tests.api.conftest import mock_munge_auth

###############################################################################
######################### /accounting/jobs ROUTE TESTS ########################
###############################################################################


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_JOBS_ENDPOINT,))
async def test_acct_jobs_session_id_filtering(client, app, endpoint):
    """Assert that /accounting/jobs can be filtered by session_id."""
    N_USERS = 2
    JOB_STATUSES = ("DONE", "ERROR")

    _, _, sessions = await acct_populate_db(
        app,
        n_users=N_USERS,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint
            + "?ended_after=2020-01-01T00:00:00"
            + f"&session_id={sessions[0].id}"
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == len(JOB_STATUSES)
    assert len(body["data"]) == len(JOB_STATUSES)
    assert all(job["session_id"] == str(sessions[0].id) for job in body["data"])


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_JOBS_ENDPOINT,))
async def test_acct_jobs_nominal(client, app, endpoint):
    """Assert that /accounting/jobs lists one row per job with its own
    status and durations."""
    N_USERS = 2

    JOB_WAIT = timedelta(seconds=30)
    JOB_EXECUTION = timedelta(seconds=60)

    EXPECTED_WAIT_TIME = int(JOB_WAIT.total_seconds())
    EXPECTED_EXECUTION_TIME = int(JOB_EXECUTION.total_seconds())

    user_uids, jobs, _ = await acct_populate_db(
        app,
        n_users=N_USERS,
        job_wait_time=JOB_WAIT,
        job_execution_time=JOB_EXECUTION,
        job_statuses=("DONE",),
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint + "?ended_after=2020-01-01T00:00:00&limit=100"
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == N_USERS
    assert len(body["data"]) == N_USERS

    for i, job_data in enumerate(body["data"]):
        assert job_data["id"] == jobs[i].id
        assert job_data["user_id"] == user_uids[i]
        assert job_data["session_id"] == str(jobs[i].session_id)
        assert job_data["status"] == "DONE"
        assert job_data["execution_time"] == EXPECTED_EXECUTION_TIME
        assert job_data["wait_time"] == EXPECTED_WAIT_TIME


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_JOBS_ENDPOINT,))
@pytest.mark.parametrize(
    "query,expected", (("", 30), ("&status=NOTASTATUS", 0), ("&status=DONE", 10))
)
async def test_acct_jobs_status_filtering(client, app, endpoint, query, expected):
    """Assert that /accounting/jobs can be filtered by Job status."""
    N_USERS = 10
    JOB_STATUSES = ("DONE", "CANCELED", "ERROR")

    await acct_populate_db(
        app,
        n_users=N_USERS,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint + "?ended_after=2020-01-01T00:00:00" + query
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == expected
    assert len(body["data"]) == expected
