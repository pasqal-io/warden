from dataclasses import replace

import pytest

from warden.api.routes.dependencies import auth


@pytest.fixture
def decoded(monkeypatch):
    """Make every MUNGE credential decode to uid 0 and the payload set by the test."""
    cred = {"payload": b""}
    monkeypatch.setattr(auth, "decode_munge", lambda _: (cred["payload"], 0))
    return cred


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
async def test_munge_audience(client, decoded, audience, payload, expected):
    """With munge_audience set, only credentials bound to the request are accepted."""
    decoded["payload"] = payload
    response = await client.get("/jobs", headers={"X-Munge-Cred": "cred"})
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_munge_audience_unset(client, decoded):
    """Without munge_audience, unbound credentials are still accepted."""
    response = await client.get("/jobs", headers={"X-Munge-Cred": "cred"})
    assert response.status_code == 200
