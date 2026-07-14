import asyncio
from datetime import datetime

import pytest

from tests.api.conftest import mock_munge_auth
from warden.api.routes.dependencies.auth import AuthConfig
from warden.lib.models import Job, Session


def set_auth_config(
    app,
    *,
    authorized_users: set[str] | None = None,
    admin_users: set[str] | None = None,
) -> None:
    current = app.state.auth_config
    app.state.auth_config = AuthConfig(
        authorized_users=(
            current.authorized_users if authorized_users is None else authorized_users
        ),
        admin_users=current.admin_users if admin_users is None else admin_users,
    )


@pytest.mark.asyncio
async def test_create_session_success(client, app):
    """Nominal test case to create a session for a user using root munge token"""
    payload = {"user_id": "1000", "slurm_job_id": "1"}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == payload["user_id"]
    assert data["qpu_slots"] == 1


@pytest.mark.asyncio
async def test_create_session_with_qpu_slots(client, app):
    """Creating a session stores requested QPU slots."""

    payload = {"user_id": "1000", "slurm_job_id": "1", "qpu_slots": 5}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 200
    assert response.json()["qpu_slots"] == 5


@pytest.mark.asyncio
async def test_create_session_rejects_invalid_qpu_slots(client, app):
    """Creating a session rejects non-positive QPU slots."""

    payload = {"user_id": "1000", "slurm_job_id": "1", "qpu_slots": 0}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_session_enforces_configured_qpu_slots(client, app):
    """Creating a session fails when active sessions exhaust QPU slots."""

    app.state.qpu_config.qpu_slots_total = 10
    payload = {"user_id": "1000", "slurm_job_id": "1", "qpu_slots": 5}
    with mock_munge_auth(app, uid=0):
        assert (await client.post("/sessions", json=payload)).status_code == 200
        assert (
            await client.post(
                "/sessions",
                json={"user_id": "1000", "slurm_job_id": "2", "qpu_slots": 5},
            )
        ).status_code == 200
        response = await client.post(
            "/sessions", json={"user_id": "1000", "slurm_job_id": "3", "qpu_slots": 1}
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_session_enforces_qpu_slots_concurrently(client, app):
    """Concurrent session creation cannot exceed configured QPU slots."""

    app.state.qpu_config.qpu_slots_total = 10
    with mock_munge_auth(app, uid=0):
        responses = await asyncio.gather(
            client.post(
                "/sessions",
                json={"user_id": "1000", "slurm_job_id": "1", "qpu_slots": 6},
            ),
            client.post(
                "/sessions",
                json={"user_id": "1000", "slurm_job_id": "2", "qpu_slots": 6},
            ),
        )
    assert sorted(response.status_code for response in responses) == [200, 409]


@pytest.mark.asyncio
async def test_create_session_is_idempotent(client, app):
    """An active scheduler job returns the original session."""

    payload = {
        "user_id": "1000",
        "slurm_job_id": "1",
        "qpu_slots": 5,
    }
    with mock_munge_auth(app, uid=0):
        first = await client.post("/sessions", json=payload)
        second = await client.post("/sessions", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_create_session_rejects_job_parameter_change(client, app):
    """An active scheduler job cannot be reused with different parameters."""

    payload = {
        "user_id": "1000",
        "slurm_job_id": "1",
        "qpu_slots": 5,
    }
    with mock_munge_auth(app, uid=0):
        assert (await client.post("/sessions", json=payload)).status_code == 200
        payload["qpu_slots"] = 4
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_revoke_session_frees_qpu_slots(client, app):
    """Revoking a session frees its QPU slots for a later session."""

    app.state.qpu_config.qpu_slots_total = 5
    payload = {"user_id": "1000", "slurm_job_id": "1", "qpu_slots": 5}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/sessions", json=payload)
        assert response.status_code == 200
        session_id = response.json()["id"]
        assert (await client.delete(f"/sessions/{session_id}")).status_code == 200
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_revoke_session_is_idempotent(client, app):
    """Repeated session revocation preserves the first revocation."""

    payload = {"user_id": "1000", "slurm_job_id": "1"}
    with mock_munge_auth(app, uid=0):
        created = await client.post("/sessions", json=payload)
        session_id = created.json()["id"]
        first = await client.delete(f"/sessions/{session_id}")
        second = await client.delete(f"/sessions/{session_id}")
    assert first.status_code == second.status_code == 200
    first_revoked_at = datetime.fromisoformat(
        first.json()["revoked_at"].rstrip("Z")
    ).replace(microsecond=0)
    second_revoked_at = datetime.fromisoformat(
        second.json()["revoked_at"].rstrip("Z")
    ).replace(microsecond=0)
    assert first_revoked_at == second_revoked_at


@pytest.mark.asyncio
async def test_create_session_non_root(client, app):
    """Creating a session using a non-root munge token should return a Forbidden error"""
    payload = {"user_id": "1000", "slurm_job_id": "1"}
    with mock_munge_auth(app, uid=1001):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_session_no_auth(client):
    """Creating a session without a munge token should return a Unauthorized error"""
    payload = {"user_id": "1000", "slurm_job_id": "1"}
    response = await client.post("/sessions", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_session_configured_admin_user(client, app):
    """Creating a session using a configured admin uid should succeed"""
    set_auth_config(app, admin_users={"1001"})

    payload = {"user_id": "1000", "slurm_job_id": "1"}
    with mock_munge_auth(app, uid=1001):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == payload["user_id"]


@pytest.mark.asyncio
async def test_create_session_non_authorized_user(client, app):
    """Creating a session using a non-authorized user when authorized_users is not empty"""
    set_auth_config(app, authorized_users={"2000"})

    payload = {"user_id": "1000", "slurm_job_id": "1"}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_session_authorized_user(client, app):
    """Creating a session using an authorized user when authorized_users is not empty"""
    set_auth_config(app, authorized_users={"1000"})

    payload = {"user_id": "1000", "slurm_job_id": "1"}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == payload["user_id"]


@pytest.mark.asyncio
async def test_revoke_session_success(client, app):
    """Nominal test case to revoke a session for a user using root munge token"""
    user_id = 1000

    async_session = app.state.db_session_factory
    new_session = Session(user_id=str(user_id), slurm_job_id="1")

    async with async_session() as session:
        session.add(new_session)
        await session.commit()
        await session.refresh(new_session)

    with mock_munge_auth(app, uid=0):
        response = await client.delete(f"/sessions/{new_session.id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_revoke_session_cancel_remaining_jobs(
    client, app, serialized_sequence: str
):
    """Nominal test case to revoke a session with pending jobs for a user using root munge token

    1. Create a session with done and pending jobs, with one of them being scheduled
    2. Call the DELETE /sessions/{session_id} endpoint
    3. Check all pending jobs have `canceled_at` set and "CANCELED" status
    4. Check that the scheduled job has `canceled_at` set and still "PENDING" status
    """
    user_id = 1000

    async_session = app.state.db_session_factory
    new_session = Session(user_id=str(user_id), slurm_job_id="1")

    async with async_session() as session:
        session.add(new_session)
        await session.commit()
        await session.refresh(new_session)

    done_jobs = [
        Job(
            sequence=serialized_sequence,
            shots=100,
            session=new_session,
            status="DONE",
            scheduled_at=datetime.now(),
        )
    ] * 5
    pending_jobs = [
        Job(sequence=serialized_sequence, shots=100, session=new_session)
    ] * 5
    scheduled_job = Job(
        sequence=serialized_sequence,
        shots=100,
        session=new_session,
        scheduled_at=datetime.now(),
    )

    async with async_session() as session:
        session.add_all(pending_jobs)
        session.add_all(done_jobs)
        session.add(scheduled_job)
        await session.commit()

        with mock_munge_auth(app, uid=0):
            response = await client.delete(f"/sessions/{new_session.id}")
        assert response.status_code == 200

        for job in pending_jobs:
            await session.refresh(job)
            assert job.canceled_at is not None
            assert job.status == "CANCELED"
        for job in done_jobs:
            await session.refresh(job)
            assert job.canceled_at is None
        await session.refresh(scheduled_job)
        assert scheduled_job.status == "PENDING"
        assert scheduled_job.canceled_at is not None
