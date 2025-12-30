import pytest

from warden.tests.conftest import mock_munge_auth


@pytest.mark.asyncio
async def test_create_session_success(client, app):
    """Nominal test case to create a session for a user using root munge token"""
    payload = {"user_id": "1000", "slurm_job_id": "1"}
    with mock_munge_auth(app, uid=0):
        response = await client.post("/sessions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == payload["user_id"]


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
