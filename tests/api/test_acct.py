from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.api.conftest import acct_populate_db, mock_munge_auth

ACCT_ENDPOINT = "/accounting"


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
        assert user_data["jobs"]["stats"][0]["total_duration"] == EXPECTED_SECONDS


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
