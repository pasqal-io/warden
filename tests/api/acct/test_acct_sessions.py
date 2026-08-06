from datetime import timedelta

import pytest

from tests.api.acct.conftest import (
    ACCT_SESSIONS_ENDPOINT,
    acct_populate_db,
)
from tests.api.conftest import mock_munge_auth

###############################################################################
####################### /accounting/sessions ROUTE TESTS ######################
###############################################################################


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_SESSIONS_ENDPOINT,))
@pytest.mark.parametrize(
    "query,expected", (("&slurm_job_id=9999", 0), ("&slurm_job_id=1", 1))
)
async def test_acct_session_slurm_job_id_filtering(
    client, app, endpoint, query, expected
):
    """Assert that /accounting/sessions can be filtered by slurm_job_id."""
    N_USERS = 10
    JOB_STATUSES = ("DONE", "ERROR")

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


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_SESSIONS_ENDPOINT,))
async def test_acct_sessions_nominal(client, app, endpoint):
    """Assert that /accounting/sessions lists one row per session with its
    own duration and job count."""
    N_USERS = 4
    JOB_STATUSES = ("DONE", "ERROR")
    SESSION_DURATION = timedelta(minutes=30)

    user_uids, _, sessions = await acct_populate_db(
        app,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint + "?ended_after=2020-01-01T00:00:00&limit=100"
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == N_USERS
    assert len(body["data"]) == N_USERS

    expected_duration = int(SESSION_DURATION.total_seconds())
    for i, session_data in enumerate(body["data"]):
        assert session_data["id"] == str(sessions[i].id)
        assert session_data["user_id"] == user_uids[i]
        assert session_data["slurm_job_id"] == sessions[i].slurm_job_id
        assert session_data["total_duration"] == expected_duration
        assert session_data["jobs_count"] == len(JOB_STATUSES)
