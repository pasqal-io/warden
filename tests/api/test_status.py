from datetime import datetime, timedelta, timezone

import pytest
from httpx2 import AsyncClient, Request, Response

from tests.api.conftest import mock_munge_auth, mock_qpu_client
from warden.lib.models import Job, Session

N_PENDING_JOBS = 10


async def _seed(
    app, *, serialized_sequence: str, no_pending: bool = False, no_running: bool = False
):
    async_session = app.state.db_session_factory

    open_session = Session(
        user_id="1000", slurm_job_id="1", created_at=datetime.now(timezone.utc)
    )
    other_sessions = [
        Session(
            user_id="1000",
            slurm_job_id="2",
            created_at=(datetime.now(timezone.utc) - timedelta(minutes=i)),
        )
        for i in range(5, 0, -1)
    ]
    revoked_session = Session(
        user_id="1000", slurm_job_id="3", revoked_at=datetime.now(timezone.utc)
    )

    async with async_session() as session:
        session.add_all([open_session, *other_sessions, revoked_session])
        await session.commit()

    pending_jobs = [
        Job(sequence=serialized_sequence, shots=100, session=open_session)
        for _ in range(N_PENDING_JOBS)
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

    jobs_to_add = [done_job]
    if not no_pending:
        jobs_to_add += pending_jobs
    if not no_running:
        jobs_to_add.append(running_job)

    async with async_session() as session:
        session.add_all(jobs_to_add)
        await session.commit()
        if not no_running:
            await session.refresh(running_job)

    return open_session, other_sessions, running_job


@pytest.mark.asyncio
async def test_get_status_non_admin(client: AsyncClient, app):
    with mock_munge_auth(app, uid=1001):
        response = await client.get("/status")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_status_no_auth(client: AsyncClient):
    response = await client.get("/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_status_admin(client: AsyncClient, app, serialized_sequence: str):
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

    assert data["pending_jobs_count"] == N_PENDING_JOBS
    assert data["current_job"]["id"] == running_job.id
    assert data["current_job"]["session_id"] == str(open_session.id)

    expected_order = [str(s.id) for s in other_sessions] + [str(open_session.id)]
    assert [s["id"] for s in data["open_sessions"]] == expected_order


@pytest.mark.asyncio
async def test_get_status_no_current_job(client: AsyncClient, app):
    """With an empty DB, current_job is null and both counts/lists are empty."""
    with mock_munge_auth(app, uid=0):
        response = await client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["pending_jobs_count"] == 0
    assert data["current_job"] is None
    assert data["open_sessions"] == []


@pytest.mark.asyncio
async def test_resource_status_online_idle_needs_no_auth(client: AsyncClient, app):

    def handler(request: Request) -> Response:
        return Response(200, json={"data": {"operational_status": "UP"}})

    with mock_qpu_client(app, handler):
        response = await client.get("/status/resource")

    assert response.status_code == 200
    assert response.json() == {
        "status": "online",
        "status_reason": "Warden ok.",
        "healthy": True,
        "busy": False,
        "pending_job_count": 0,
        "capacity": None,
    }


@pytest.mark.asyncio
async def test_resource_status_follow_accessible(client: AsyncClient, app):
    payload = {"is_accessible": False, "message": "Scheduled QPU maintenance"}
    with mock_munge_auth(app, uid=0):
        assert (await client.post("/accessible", json=payload)).status_code == 200

    body = (await client.get("/status/resource")).json()

    assert body["status"] == "paused"
    assert body["status_reason"] == "Scheduled QPU maintenance"

    payload = {"is_accessible": True, "message": "Back up!"}
    with mock_munge_auth(app, uid=0):
        assert (await client.post("/accessible", json=payload)).status_code == 200

    body = (await client.get("/status/resource")).json()

    assert body["status"] == "online"
    assert body["status_reason"] == "Back up!"


@pytest.mark.asyncio
async def test_resource_status_busy_counts_pending_jobs(
    client: AsyncClient, app, serialized_sequence: str
):
    await _seed(app, serialized_sequence=serialized_sequence, no_running=True)

    body = (await client.get("/status/resource")).json()

    assert body["busy"] is True  # No running job
    assert body["pending_job_count"] == N_PENDING_JOBS


@pytest.mark.asyncio
async def test_resource_status_busy_counts_running_job(
    client: AsyncClient, app, serialized_sequence: str
):
    await _seed(app, serialized_sequence=serialized_sequence, no_pending=True)

    body = (await client.get("/status/resource")).json()

    assert body["busy"] is True  # One running job
    assert body["pending_job_count"] == 0


@pytest.mark.asyncio
async def test_resource_status_qpu_status_up(client: AsyncClient, app):

    def handler(request: Request) -> Response:
        return Response(200, json={"data": {"operational_status": "UP"}})

    with mock_qpu_client(app, handler=handler):
        body = (await client.get("status/resource")).json()

    assert body["healthy"] is True


@pytest.mark.asyncio
async def test_resource_status_qpu_status_down(client: AsyncClient, app):

    def handler(request: Request) -> Response:
        return Response(200, json={"data": {"operational_status": "DOWN"}})

    with mock_qpu_client(app, handler=handler):
        body = (await client.get("status/resource")).json()

    assert body["healthy"] is False


@pytest.mark.asyncio
async def test_resource_status_qpu_status_no_info(client: AsyncClient, app):

    def handler(request: Request) -> Response:
        return Response(200, json={"data": {}})

    with mock_qpu_client(app, handler=handler):
        body = (await client.get("status/resource")).json()

    assert body["healthy"] is None


@pytest.mark.asyncio
async def test_resource_status_qpu_status_no_qpu(client: AsyncClient, app):

    def handler(request: Request) -> Response:
        return Response(503, json={"error": "QPU unavailable"})

    with mock_qpu_client(app, handler=handler):
        body = (await client.get("status/resource")).json()

    assert body["healthy"] is False
