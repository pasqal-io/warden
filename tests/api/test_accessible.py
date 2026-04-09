import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_accessible_nominal(client: AsyncClient, app):
    """Test nominal behavior where warden is accessible"""

    # Call to the endpoint
    response = await client.get("/accessible")
    assert response.status_code == 200
    assert response.json()["is_accessible"]
