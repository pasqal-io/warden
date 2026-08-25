from datetime import datetime, timedelta, timezone

import pytest

from tests.api.conftest import mock_munge_auth
from warden.lib.models import Job, Session


async def _seed(app, *, serialized_sequence: str):
    async_session = app.state.db_session_factory

    open_session = Session(
        user_id="1000", slurm_job_id="1", created_at=datetime.now(timezone.utc)
    )
    other_sessions = [
        Session(
            user_id="1000",
            slurm_job_id="1",
            created_at=(datetime.now(timezone.utc) - timedelta(minutes=i)),
        )
        for i in range(1, 6)
    ]
    revoked_session = Session(
        user_id="1000", slurm_job_id="2", revoked_at=datetime.now(timezone.utc)
    )

    async with async_session() as session:
        session.add_all([open_session, *other_sessions, revoked_session])
        await session.commit()

    pending_jobs = [
        Job(sequence=serialized_sequence, shots=100, session=open_session)
        for _ in range(10)
    ]
    running_job = Job(
        sequence=serialized_sequence,
        shots=100,
        session=open_session,
        status="RUNNING",
        scheduled_at=datetime.now(),
        started_at=datetime.now(),
    )
    done_job = Job(
        sequence=serialized_sequence,
        shots=100,
        session=open_session,
        status="DONE",
        scheduled_at=datetime.now(),
        started_at=datetime.now(),
        ended_at=datetime.now(),
    )

    async with async_session() as session:
        session.add_all([*pending_jobs, running_job, done_job])
        await session.commit()
        await session.refresh(running_job)

    return open_session, other_sessions, running_job


@pytest.mark.asyncio
async def test_get_status_non_admin(client, app):
    with mock_munge_auth(app, uid=1001):
        response = await client.get("/status")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_status_no_auth(client):
    response = await client.get("/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_status_admin(client, app, serialized_sequence: str):
    """A PENDING, RUNNING and DONE job plus several open sessions and a
    revoked session are seeded; the snapshot must count only the PENDING job,
    surface the RUNNING job as current_job (ignoring DONE), and list the open
    sessions ordered by creation time, oldest first."""
    open_session, other_sessions, running_job = await _seed(
        app, serialized_sequence=serialized_sequence
    )

    with mock_munge_auth(app, uid=0):
        response = await client.get("/status")
    assert response.status_code == 200
    data = response.json()

    assert data["pending_jobs_count"] == 10
    assert data["current_job"]["id"] == running_job.id
    assert data["current_job"]["session_id"] == str(open_session.id)

    expected_order = [str(s.id) for s in reversed(other_sessions)] + [
        str(open_session.id)
    ]
    assert [s["id"] for s in data["open_sessions"]] == expected_order


@pytest.mark.asyncio
async def test_get_status_no_current_job(client, app):
    """With an empty DB, current_job is null and both counts/lists are empty."""
    with mock_munge_auth(app, uid=0):
        response = await client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["pending_jobs_count"] == 0
    assert data["current_job"] is None
    assert data["open_sessions"] == []
