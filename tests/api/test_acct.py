from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

from tests.api.conftest import acct_populate_db, mock_munge_auth
from warden.api.schemas.acct import AcctRequest

ACCT_ENDPOINT = "/accounting"
ACCT_SESSIONS_ENDPOINT = "/accounting/sessions"
ACCT_JOBS_ENDPOINT = "/accounting/jobs"
ACCT_ENDPOINTS = [ACCT_ENDPOINT, ACCT_JOBS_ENDPOINT, ACCT_SESSIONS_ENDPOINT]

###############################################################################
############################### ACCT QUERY TESTS ##############################
###############################################################################


def test_acct_request_normalizes_datetimes_to_utc():
    """The `ended_after`/`ended_before` validator must produce UTC-aware
    values regardless of the offset supplied by the caller, since not every
    supported DB backend preserves timezone info on stored columns."""

    naive_utc = datetime(2026, 1, 1, 12, 0, 0)
    aware_utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    aware_non_utc = naive_utc.replace(tzinfo=timezone(timedelta(hours=2))) + timedelta(
        hours=2
    )

    req = AcctRequest(ended_after=aware_non_utc, ended_before=aware_non_utc)
    assert req.ended_after == aware_utc
    assert req.ended_before == aware_utc

    # Naive input is assumed to already be UTC and passed through unchanged.
    req_naive = AcctRequest(ended_after=naive_utc)
    assert req_naive.ended_after == aware_utc
    assert req_naive.ended_after is not None
    assert req_naive.ended_after.tzinfo is timezone.utc

    # ended_before is optional; None must pass through untouched.
    assert req_naive.ended_before is None


###############################################################################
############################## COMMON ROUTE TESTS #############################
###############################################################################


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ACCT_ENDPOINTS)
@pytest.mark.parametrize(
    "query, expected_start, expected_end, expected_len, expected_first_index",
    [
        ("limit=100", 0, 10, 10, 0),
        ("limit=5", 0, 5, 5, 0),
        ("limit=5&offset=4", 4, 9, 5, 4),
        ("offset=8", 8, 10, 2, 8),
        # Offset past the end: the page is empty, and start/end are clamped to
        # total so the response stays consistent (end - start == 0 items, never
        # pointing beyond the data).
        ("offset=20", 10, 10, 0, None),
    ],
)
async def test_acct_pagination(
    client,
    app,
    endpoint,
    query,
    expected_start,
    expected_end,
    expected_len,
    expected_first_index,
):
    """Assert that the accounting data query returns the right number of rows for each of the endpoints.

    We create 10 users, each with one session and one job in the session,
    - /accounting
    - /accounting/jobs
    - /accounting/sessions
    Then all have the same number of rows (10) so we can test their pagination similarly
    """
    N_USERS = 10

    user_uids, _, _ = await acct_populate_db(app, N_USERS, job_statuses=("DONE",))

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint + f"?ended_after=2020-01-01T00:00:00&{query}"
        )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == N_USERS
    assert response.json()["pagination"]["start"] == expected_start
    assert response.json()["pagination"]["end"] == expected_end
    assert len(response.json()["data"]) == expected_len
    if expected_first_index is not None:
        assert response.json()["data"][0]["user_id"] == user_uids[expected_first_index]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ACCT_ENDPOINTS)
async def test_acct_user_id_filtering(client, app, endpoint):
    """Test that accounting routes correctly filter by user_ids

    Rationale:
    - Populate DB with 10 users with each one session with one job
    - So, for any route, len(data) = number of user_id selected
    """

    N_USERS = 10

    user_ids, _, _ = await acct_populate_db(
        app,
        N_USERS,
    )

    # No filter
    with mock_munge_auth(app, uid=0):
        response = await client.get(endpoint + "?ended_after=1999-01-01&limit=10")
    assert response.status_code == 200
    assert len(response.json()["data"]) == N_USERS

    # Filter with all user_ids
    with mock_munge_auth(app, uid=0):
        request = endpoint + "?ended_after=1999-01-01&limit=10"
        for user_id in user_ids:
            request += "&user_ids=" + user_id
        response = await client.get(request)
    assert response.status_code == 200
    assert len(response.json()["data"]) == N_USERS

    # Filter with 3 existing user_ids
    selected_ids = user_ids[:3]
    with mock_munge_auth(app, uid=0):
        request = endpoint + "?ended_after=1999-01-01&limit=10"
        for user_id in selected_ids:
            request += "&user_ids=" + user_id
        response = await client.get(request)
    assert response.status_code == 200
    assert len(response.json()["data"]) == 3
    for row in response.json()["data"]:
        assert row["user_id"] in selected_ids

    # Filter with a non-existent user_id
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint
            + "?ended_after=1999-01-01&limit=10"
            + "&user_ids=9999999999999999999999999"
        )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ACCT_ENDPOINTS)
async def test_acct_datetime_filter(client, app, endpoint):
    """Assert that the accounting data query correctly filters sessions according to start/end datetime."""

    N_USERS = 10
    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)

    SESSION_DURATION = timedelta(minutes=45)
    USER_TIME_OFFSET = timedelta(hours=1)

    user_ids, _, sessions = await acct_populate_db(
        app,
        first_session_start=FIRST_SESSION_START,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        user_time_offset=USER_TIME_OFFSET,
        job_statuses=("DONE",),
    )

    # Test default get all
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint + "?ended_after=" + FIRST_SESSION_START.isoformat()
        )
    assert response.status_code == 200
    assert len(response.json()["data"]) == N_USERS
    assert response.json()["data"][0]["user_id"] == user_ids[0]

    # Test filtering only first user session
    first_session = sessions[0]
    assert first_session.revoked_at is not None
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT
            + "?ended_after="
            + FIRST_SESSION_START.isoformat()
            + "&ended_before="
            + (first_session.revoked_at + timedelta(seconds=1)).isoformat()
        )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["user_id"] == user_ids[0]

    # Test time filtering is total partition of data
    # We split the filtering exactly at the revocation time of the 2nd user's session
    second_session = sessions[1]
    assert second_session.revoked_at is not None
    with mock_munge_auth(app, uid=0):
        response_before = await client.get(
            endpoint
            + "?ended_after="
            + FIRST_SESSION_START.isoformat()
            + "&ended_before="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
        response_after = await client.get(
            endpoint
            + "?ended_after="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
    assert response_after.status_code == 200
    assert response_before.status_code == 200

    assert len(response_before.json()["data"]) == 1
    assert len(response_after.json()["data"]) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ACCT_ENDPOINTS)
async def test_acct_datetime_filter_accepts_timezone_aware_query_params(
    client, app, endpoint
):
    """Assert that a ended_after with a non-UTC offset selects the same
    rows as its naive-UTC equivalent, i.e. the request-level normalization
    is actually applied to query params, not just direct model usage."""

    N_USERS = 10
    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)
    SESSION_DURATION = timedelta(minutes=45)
    USER_TIME_OFFSET = timedelta(hours=1)

    _, _, sessions = await acct_populate_db(
        app,
        first_session_start=FIRST_SESSION_START,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        user_time_offset=USER_TIME_OFFSET,
    )

    second_session = sessions[1]
    assert second_session.revoked_at is not None

    # Same instant as `revoked_at` (naive, assumed UTC), expressed at UTC+2.
    aware_equivalent = (second_session.revoked_at + timedelta(hours=2)).replace(
        tzinfo=timezone(timedelta(hours=2))
    )

    with mock_munge_auth(app, uid=0):
        response_naive = await client.get(
            endpoint
            + "?ended_after="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
        response_aware = await client.get(
            endpoint
            + "?ended_after="
            # `+` is form-encoding shorthand for a space in query strings, so
            # a raw `+HH:MM` offset must be percent-encoded, same as any real
            # HTTP client does automatically (e.g. httpx's `params=` kwarg).
            + quote(aware_equivalent.isoformat())
            + "&limit=100"
        )
    assert response_naive.status_code == 200
    assert response_aware.status_code == 200
    assert response_naive.json()["data"] == response_aware.json()["data"]


###############################################################################
############################ /accounting ROUTE TESTS ##########################
###############################################################################


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_ENDPOINT,))
async def test_acct_nominal(client, app, endpoint):
    """Assert that /accounting lists one row per user with its session and
    job summaries (counts and durations) correctly aggregated."""
    N_USERS = 3
    JOB_STATUSES = ("DONE", "ERROR")
    SESSION_DURATION = timedelta(minutes=30)
    JOB_WAIT = timedelta(seconds=15)
    JOB_EXECUTION = timedelta(seconds=45)

    user_uids, _, _ = await acct_populate_db(
        app,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        job_statuses=JOB_STATUSES,
        job_wait_time=JOB_WAIT,
        job_execution_time=JOB_EXECUTION,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint + "?ended_after=2020-01-01T00:00:00&limit=100"
        )
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
        assert {stat["status"] for stat in user_data["jobs"]["stats"]} == set(
            JOB_STATUSES
        )
        for stat in user_data["jobs"]["stats"]:
            assert stat["count"] == 1
            assert stat["execution_time"] == expected_execution_time
            assert stat["wait_time"] == expected_wait_time


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_ENDPOINT,))
async def test_acct_session_without_jobs(client, app, endpoint):
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
        response = await client.get(
            endpoint + "?ended_after=2020-01-01T00:00:00&limit=100"
        )
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
async def test_acct_reported_durations(client, app, endpoint):
    """Assert that reported session and job durations are the real elapsed seconds.

    The aggregation uses ``extract('epoch', ...)``, which only has the intended
    meaning on PostgreSQL. This pins the value on every supported backend.
    """
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
        response = await client.get(
            endpoint + "?ended_after=2020-01-01T00:00:00&limit=100"
        )
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


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", (ACCT_ENDPOINT,))
async def test_acct_jobs_are_aligned_with_paginated_users(client, app, endpoint):
    """Assert that job stats belong to the users on the returned page.

    The sessions aggregation groups by user, the jobs aggregation groups by
    (user, status). Paginating both with the same offset/limit only lines up
    when every user has exactly one status, so we test by giving each user several.
    """
    N_USERS = 6
    JOB_STATUSES = ("DONE", "ERROR", "CANCELED")
    PAGINATION_LIMIT = 3
    PAGINATION_OFFSET = 3
    assert PAGINATION_LIMIT + PAGINATION_OFFSET <= N_USERS

    user_uids, _, _ = await acct_populate_db(
        app,
        n_users=N_USERS,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            endpoint
            + f"?ended_after=2020-01-01T00:00:00&limit={PAGINATION_LIMIT}"
            + f"&offset={PAGINATION_OFFSET}"
        )
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == PAGINATION_LIMIT

    expected_uids = user_uids[PAGINATION_OFFSET : PAGINATION_OFFSET + PAGINATION_LIMIT]
    assert [user_data["user_id"] for user_data in data] == expected_uids

    for user_data in data:
        # Each user on the page owns exactly one job per status.
        assert user_data["jobs"]["count"] == len(JOB_STATUSES), (
            f"user {user_data['user_id']} reported {user_data['jobs']['count']} "
            f"jobs, expected {len(JOB_STATUSES)}"
        )
        assert {stat["status"] for stat in user_data["jobs"]["stats"]} == set(
            JOB_STATUSES
        )
        for stat in user_data["jobs"]["stats"]:
            assert stat["count"] == 1


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
    # TODO: check content of data ?


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
    # TODO: check content of data ?


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
