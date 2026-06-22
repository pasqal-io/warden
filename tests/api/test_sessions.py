import pytest

from tests.api.conftest import mock_munge_auth
from warden.api.routes.dependencies.auth import AuthConfig


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
