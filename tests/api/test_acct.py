from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.api.conftest import acct_populate_db, mock_munge_auth

ACCT_ENDPOINT = "/acct"


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
