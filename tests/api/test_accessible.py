import pytest
from conftest import mock_munge_auth
from httpx import AsyncClient


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

    1. Update the endpoint with root munge token and set 'is_accessible' to False
    2. Get the accessibility status at /accessible
    3. Update the endpoint again with root munge token and set 'is_accessible' to True
    4. Get the accessibility status again

    """

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
