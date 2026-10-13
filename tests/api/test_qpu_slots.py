import pytest
from httpx import AsyncClient

from warden.lib.models import Session


@pytest.mark.asyncio
async def test_qpu_slots_requires_configured_capacity(client: AsyncClient):
    """GET /qpu-slots rejects a Warden without slot capacity."""

    response = await client.get("/qpu-slots")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_qpu_slots_reports_configured_capacity(client: AsyncClient, app):
    """GET /qpu-slots reports active session usage."""

    app.state.qpu_config.qpu_slots_total = 10
    async with app.state.db_session_factory() as session:
        session.add(Session(user_id="1000", scheduler_job_id="1", qpu_slots=4))
        await session.commit()

    response = await client.get("/qpu-slots")

    assert response.status_code == 200
    assert response.json() == {
        "qpu_slots_total": 10,
        "qpu_slots_used": 4,
        "qpu_slots_available": 6,
    }
