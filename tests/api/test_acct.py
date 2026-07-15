from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.api.conftest import mock_munge_auth
from warden.lib.models import Job, Session

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
async def test_acct_nominal_pagination(client, app, serialized_sequence):
    """Assert that the accounting data query returns the right number of rows."""
    START_DATETIME = datetime(2026, 1, 1, 0, 0, 0)
    END_DATETIME = datetime(2026, 1, 1, 1, 0, 0)
    N_USERS = 10
    user_uids = [str(i) for i in range(1000, 1000 + N_USERS)]

    # Create at least one session and job per user
    sessions = []
    jobs = []
    for i, uid in enumerate(user_uids):
        start_session = START_DATETIME + timedelta(hours=i)
        end_session = END_DATETIME + timedelta(hours=i)

        sessions.append(
            Session(
                created_at=start_session,
                revoked_at=end_session,
                user_id=uid,
                slurm_job_id=str(i),
            )
        )
        jobs.append(
            Job(
                status="DONE",
                logs="",
                shots=100,
                sequence=serialized_sequence,
                created_at=start_session,
                scheduled_at=start_session,
                started_at=start_session,
                ended_at=end_session,
                # Relationship
                session=sessions[-1],
            )
        )

    async_session_factory = app.state.db_session_factory
    async with async_session_factory() as db_session:
        db_session.add_all(sessions)
        db_session.add_all(jobs)
        await db_session.commit()

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
