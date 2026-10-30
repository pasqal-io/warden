from dataclasses import replace

import pytest

from tests.api.conftest import mock_munge_auth


@pytest.fixture
def audience(app):
    app.state.auth_config = replace(
        app.state.auth_config, munge_audience=frozenset({"http://warden:4207"})
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, expected",
    [
        (b"GET http://warden:4207/jobs", 200),
        (b"GET http://evil:4207/jobs", 401),  # minted for another server
        (b"POST http://warden:4207/jobs", 401),  # another method
        (b"GET http://warden:4207/sessions", 401),  # another path
        (b"", 401),  # unbound, as before this check
    ],
)
async def test_munge_audience(client, app, audience, payload, expected):
    """With munge_audience set, only credentials bound to the request are accepted."""
    with mock_munge_auth(app, uid=0, payload=payload):
        response = await client.get("/jobs")
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_munge_audience_unset(client, app):
    """Without munge_audience, unbound credentials are still accepted."""
    with mock_munge_auth(app, uid=0):
        response = await client.get("/jobs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_munge_audience_admin_route(client, app, audience):
    """Admin routes check the binding too."""
    with mock_munge_auth(app, uid=0, payload=b"GET http://evil:4207/status"):
        response = await client.get("/status")
    assert response.status_code == 401
    with mock_munge_auth(app, uid=0, payload=b"GET http://warden:4207/status"):
        response = await client.get("/status")
    assert response.status_code == 200
