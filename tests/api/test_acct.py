from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest
from httpx import AsyncClient

from tests.api.conftest import acct_populate_db, mock_munge_auth
from warden.api.schemas.acct import AcctRequest

ACCT_ENDPOINT = "/accounting"
ACCT_SESSIONS_ENDPOINT = "/accounting/sessions"
ACCT_JOBS_ENDPOINT = "/accounting/jobs"


@pytest.mark.asyncio
async def test_acct_required_start(client: AsyncClient, app):
    """Assert that 'start_datetime' is required in the accounting data query."""

    with mock_munge_auth(app, uid=0):
        response = await client.get(ACCT_ENDPOINT)
    assert response.status_code == 422

    with mock_munge_auth(app, uid=0):
        response = await client.get(ACCT_ENDPOINT + "?end_datetime=2022-01-01T00:00:00")
    assert response.status_code == 422

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT + "?start_datetime=2022-01-01T00:00:00"
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_acct_nominal_pagination_filter(client, app, serialized_sequence):
    """Assert that the accounting data query returns the right number of rows."""
    N_USERS = 10

    user_uids, _, _ = await acct_populate_db(app, serialized_sequence, N_USERS)

    # Test default
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT + "?start_datetime=2020-01-01T00:00:00&limit=100"
        )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == N_USERS
    assert response.json()["pagination"]["start"] == 0
    assert response.json()["pagination"]["end"] == N_USERS
    assert len(response.json()["data"]) == N_USERS
    assert response.json()["data"][0]["user_id"] == user_uids[0]

    # Test pagination limit
    PAGINATION_LIMIT = 5
    assert PAGINATION_LIMIT < N_USERS

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT
            + f"?start_datetime=2020-01-01T00:00:00&limit={PAGINATION_LIMIT}"
        )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == N_USERS
    assert response.json()["pagination"]["start"] == 0
    assert response.json()["pagination"]["end"] == PAGINATION_LIMIT
    assert len(response.json()["data"]) == PAGINATION_LIMIT
    assert response.json()["data"][0]["user_id"] == user_uids[0]

    # Test offset
    PAGINATION_LIMIT = 5
    PAGINATION_OFFSET = 4
    assert PAGINATION_LIMIT + PAGINATION_OFFSET < N_USERS

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT
            + f"?start_datetime=2020-01-01T00:00:00&limit={PAGINATION_LIMIT}&offset={PAGINATION_OFFSET}"
        )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == N_USERS
    assert response.json()["pagination"]["start"] == PAGINATION_OFFSET
    assert response.json()["pagination"]["end"] == PAGINATION_LIMIT + PAGINATION_OFFSET
    assert len(response.json()["data"]) == PAGINATION_LIMIT
    assert response.json()["data"][0]["user_id"] == user_uids[PAGINATION_OFFSET]

    # Test offset end of data length
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT + f"?start_datetime=2020-01-01T00:00:00&offset={N_USERS - 2}"
        )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == N_USERS
    assert response.json()["pagination"]["start"] == N_USERS - 2
    assert response.json()["pagination"]["end"] == N_USERS
    assert len(response.json()["data"]) == 2
    assert response.json()["data"][0]["user_id"] == user_uids[N_USERS - 2]

    # Test offset past the end: the page is empty, and start/end are clamped to
    # total so the response stays consistent (end - start == 0 items, never
    # pointing beyond the data).
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT + f"?start_datetime=2020-01-01T00:00:00&offset={N_USERS + 10}"
        )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == N_USERS
    assert response.json()["pagination"]["start"] == N_USERS
    assert response.json()["pagination"]["end"] == N_USERS
    assert len(response.json()["data"]) == 0


@pytest.mark.asyncio
async def test_acct_nominal_datetime_filter(client, app, serialized_sequence):
    """Assert that the accounting data query correctly filters according to start/end datetime."""

    N_USERS = 10
    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)

    SESSION_DURATION = timedelta(minutes=45)
    USER_TIME_OFFSET = timedelta(hours=1)

    user_ids, _, sessions = await acct_populate_db(
        app,
        serialized_sequence,
        first_session_start=FIRST_SESSION_START,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        user_time_offset=USER_TIME_OFFSET,
    )

    # Test default get all
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT + "?start_datetime=" + FIRST_SESSION_START.isoformat()
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
            + "?start_datetime="
            + FIRST_SESSION_START.isoformat()
            + "&end_datetime="
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
            ACCT_ENDPOINT
            + "?start_datetime="
            + FIRST_SESSION_START.isoformat()
            + "&end_datetime="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
        response_after = await client.get(
            ACCT_ENDPOINT
            + "?start_datetime="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
    assert response_after.status_code == 200
    assert response_before.status_code == 200

    assert len(response_before.json()["data"]) == 1
    assert len(response_after.json()["data"]) == 9


def test_acct_request_normalizes_datetimes_to_naive_utc():
    """The `start_datetime`/`end_datetime` validator must produce naive UTC
    values regardless of the offset supplied by the caller, since not every
    supported DB backend preserves timezone info on stored columns."""

    naive_utc = datetime(2026, 1, 1, 12, 0, 0)
    aware_non_utc = naive_utc.replace(tzinfo=timezone(timedelta(hours=2))) + timedelta(
        hours=2
    )

    req = AcctRequest(start_datetime=aware_non_utc, end_datetime=aware_non_utc)
    assert req.start_datetime == naive_utc
    assert req.start_datetime.tzinfo is None
    assert req.end_datetime == naive_utc
    assert req.end_datetime.tzinfo is None

    # Naive input is assumed to already be UTC and passed through unchanged.
    req_naive = AcctRequest(start_datetime=naive_utc)
    assert req_naive.start_datetime == naive_utc
    assert req_naive.start_datetime.tzinfo is None

    # end_datetime is optional; None must pass through untouched.
    assert req_naive.end_datetime is None


@pytest.mark.asyncio
async def test_acct_datetime_filter_accepts_timezone_aware_query_params(
    client, app, serialized_sequence
):
    """Assert that a start_datetime with a non-UTC offset selects the same
    rows as its naive-UTC equivalent, i.e. the request-level normalization
    is actually applied to query params, not just direct model usage."""

    N_USERS = 10
    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)
    SESSION_DURATION = timedelta(minutes=45)
    USER_TIME_OFFSET = timedelta(hours=1)

    _, _, sessions = await acct_populate_db(
        app,
        serialized_sequence,
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
            ACCT_ENDPOINT
            + "?start_datetime="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
        response_aware = await client.get(
            ACCT_ENDPOINT
            + "?start_datetime="
            # `+` is form-encoding shorthand for a space in query strings, so
            # a raw `+HH:MM` offset must be percent-encoded, same as any real
            # HTTP client does automatically (e.g. httpx's `params=` kwarg).
            + quote(aware_equivalent.isoformat())
            + "&limit=100"
        )
    assert response_naive.status_code == 200
    assert response_aware.status_code == 200
    assert response_naive.json()["data"] == response_aware.json()["data"]


@pytest.mark.asyncio
async def test_acct_reported_durations(client, app, serialized_sequence):
    """Assert that reported session and job durations are the real elapsed seconds.

    The aggregation uses ``extract('epoch', ...)``, which only has the intended
    meaning on PostgreSQL. This pins the value on every supported backend.
    """
    N_USERS = 3
    SESSION_DURATION = timedelta(hours=1)
    EXPECTED_SECONDS = int(SESSION_DURATION.total_seconds())

    await acct_populate_db(
        app,
        serialized_sequence,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT + "?start_datetime=2020-01-01T00:00:00&limit=100"
        )
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == N_USERS

    for user_data in data:
        # One session of SESSION_DURATION per user.
        assert user_data["sessions"]["count"] == 1
        assert user_data["sessions"]["total_duration"] == EXPECTED_SECONDS

        # One job, spanning the whole session.
        assert user_data["jobs"]["count"] == 1
        assert len(user_data["jobs"]["stats"]) == 1
        assert user_data["jobs"]["stats"][0]["execution_time"] == EXPECTED_SECONDS
        assert user_data["jobs"]["stats"][0]["wait_time"] == 0


@pytest.mark.asyncio
async def test_acct_jobs_are_aligned_with_paginated_users(
    client, app, serialized_sequence
):
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
        serialized_sequence,
        n_users=N_USERS,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT
            + f"?start_datetime=2020-01-01T00:00:00&limit={PAGINATION_LIMIT}"
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


@pytest.mark.asyncio
async def test_acct_user_filtering(client, app, serialized_sequence):
    """Assert that accounting data can be filtered by user"""

    N_USERS = 10
    JOB_STATUSES = ("DONE", "ERROR", "CANCELED")

    user_uids, _, _ = await acct_populate_db(
        app,
        serialized_sequence,
        n_users=N_USERS,
        job_statuses=JOB_STATUSES,
    )

    # Filter with a single user
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT
            + "?start_datetime=2020-01-01T00:00:00"
            + f"&user_ids={user_uids[0]}"
        )
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["user_id"] == user_uids[0]

    # Filter with several users
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT
            + "?start_datetime=2020-01-01T00:00:00"
            + f"&user_ids={user_uids[0]}"
            + f"&user_ids={user_uids[1]}"
            + f"&user_ids={user_uids[2]}"
            + f"&user_ids={user_uids[3]}"
        )
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 4
    assert data[0]["user_id"] == user_uids[0]
    assert data[1]["user_id"] == user_uids[1]
    assert data[2]["user_id"] == user_uids[2]
    assert data[3]["user_id"] == user_uids[3]

    # Filter with non-existing user
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_ENDPOINT + "?start_datetime=2020-01-01T00:00:00" + "&user_ids=9999999"
        )
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 0


@pytest.mark.asyncio
async def test_acct_jobs_user_filtering(client, app, serialized_sequence):
    """Assert that /accounting/jobs filters by user and reports the right count."""
    N_USERS = 3
    JOB_STATUSES = ("DONE", "ERROR")

    user_uids, _, _ = await acct_populate_db(
        app,
        serialized_sequence,
        n_users=N_USERS,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_JOBS_ENDPOINT
            + "?start_datetime=2020-01-01T00:00:00"
            + f"&user_ids={user_uids[0]}"
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == len(JOB_STATUSES)
    assert len(body["data"]) == len(JOB_STATUSES)
    assert all(job["user_id"] == user_uids[0] for job in body["data"])


@pytest.mark.asyncio
async def test_acct_jobs_session_id_filtering(client, app, serialized_sequence):
    """Assert that /accounting/jobs can be filtered by session_id."""
    N_USERS = 2
    JOB_STATUSES = ("DONE", "ERROR")

    _, _, sessions = await acct_populate_db(
        app,
        serialized_sequence,
        n_users=N_USERS,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_JOBS_ENDPOINT
            + "?start_datetime=2020-01-01T00:00:00"
            + f"&session_id={sessions[0].id}"
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == len(JOB_STATUSES)
    assert len(body["data"]) == len(JOB_STATUSES)
    assert all(job["session_id"] == str(sessions[0].id) for job in body["data"])


@pytest.mark.asyncio
async def test_acct_sessions_nominal(client, app, serialized_sequence):
    """Assert that /accounting/sessions lists one row per session with its
    own duration and job count."""
    N_USERS = 4
    JOB_STATUSES = ("DONE", "ERROR")
    SESSION_DURATION = timedelta(minutes=30)

    user_uids, _, sessions = await acct_populate_db(
        app,
        serialized_sequence,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        job_statuses=JOB_STATUSES,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_SESSIONS_ENDPOINT + "?start_datetime=2020-01-01T00:00:00&limit=100"
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == N_USERS
    assert len(body["data"]) == N_USERS

    expected_duration = int(SESSION_DURATION.total_seconds())
    for i, session_data in enumerate(body["data"]):
        assert session_data["id"] == str(sessions[i].id)
        assert session_data["user_id"] == user_uids[i]
        assert session_data["total_duration"] == expected_duration
        assert session_data["jobs_count"] == len(JOB_STATUSES)


@pytest.mark.asyncio
async def test_acct_jobs_nominal(client, app, serialized_sequence):
    """Assert that /accounting/jobs lists one row per job with its own
    status and durations."""
    N_USERS = 2
    SESSION_DURATION = timedelta(minutes=20)

    user_uids, jobs, _ = await acct_populate_db(
        app,
        serialized_sequence,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            ACCT_JOBS_ENDPOINT + "?start_datetime=2020-01-01T00:00:00&limit=100"
        )
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == N_USERS
    assert len(body["data"]) == N_USERS

    expected_execution_time = int(SESSION_DURATION.total_seconds())
    for i, job_data in enumerate(body["data"]):
        assert job_data["id"] == jobs[i].id
        assert job_data["user_id"] == user_uids[i]
        assert job_data["status"] == "DONE"
        assert job_data["execution_time"] == expected_execution_time
        assert job_data["wait_time"] == 0
