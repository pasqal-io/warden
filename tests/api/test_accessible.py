import pytest
from httpx import AsyncClient

from tests.api.conftest import mock_munge_auth
from warden.lib.models import Session


@pytest.mark.asyncio
async def test_accessible_nominal(client: AsyncClient, app):
    """Test nominal behavior where warden is accessible"""

    # Call to the endpoint
    response = await client.get("/accessible")
    assert response.status_code == 200
    assert response.json()["is_accessible"]


@pytest.mark.asyncio
async def test_accessible_update(client: AsyncClient, app):
    """Test updating Warden accessibility and check the update:

    1. Get the accessibility status at /accessible before any update
        to check default behavior
    2. Update the endpoint with root munge token and set 'is_accessible' to False
    3. Get the accessibility status at /accessible
    4. Update the endpoint again with root munge token and set 'is_accessible' to True
    5. Get the accessibility status again
    """

    # Call the endpoint before any update for default behavior
    response = await client.get("/accessible")
    assert response.status_code == 200
    assert response.json()["is_accessible"]

    # Update the endpoint
    payload = {"is_accessible": False, "message": "Updated"}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/accessible", json=payload)
    assert response.status_code == 200
    assert not response.json()["is_accessible"]

    # Call the endpoint to check the update
    response = await client.get("/accessible")
    assert response.status_code == 200
    assert not response.json()["is_accessible"]
    assert response.json()["message"] == "Updated"

    # Update the endpoint again
    payload = {"is_accessible": True, "message": "Updated again"}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/accessible", json=payload)
    assert response.status_code == 200
    assert response.json()["is_accessible"]

    # Call the endpoint to check the update
    response = await client.get("/accessible")
    assert response.status_code == 200
    assert response.json()["is_accessible"]
    assert response.json()["message"] == "Updated again"


@pytest.mark.asyncio
async def test_accessible_auth_update(client: AsyncClient, app):
    """Test update of the accessibility only available to root user"""

    payload = {"is_accessible": False, "message": "Updated"}
    with mock_munge_auth(app, uid=1000):
        response = await client.post("/accessible", json=payload)
    assert response.status_code == 403

    with mock_munge_auth(app, uid=0):
        response = await client.post("/accessible", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_accessible_get_contract_for_external_polling(client: AsyncClient):
    """Verify GET /accessible is unauthenticated and schema-stable."""

    response = await client.get("/accessible")
    assert response.status_code == 200
    assert {"is_accessible", "message"}.issubset(response.json())
    assert isinstance(response.json()["is_accessible"], bool)
    assert isinstance(response.json()["message"], str)


@pytest.mark.asyncio
async def test_accessible_reports_configured_qpu_slots(client: AsyncClient, app):
    """Verify GET /accessible includes configured QPU slot capacity."""

    app.state.qpu_config.qpu_slots_total = 10
    async_session = app.state.db_session_factory
    async with async_session() as session:
        session.add(Session(user_id="1000", slurm_job_id="1", qpu_slots=4))
        await session.commit()

    response = await client.get("/accessible")

    assert response.status_code == 200
    assert response.json()["qpu_slots_total"] == 10
    assert response.json()["qpu_slots_used"] == 4
    assert response.json()["qpu_slots_available"] == 6
