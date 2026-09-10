"""Testing lib/qpu_client/auth"""

import json
import logging

import pytest
from httpx2 import AsyncClient, HTTPStatusError
from pytest_httpx2 import HTTPXMock

from warden.lib.config.config import QPUAuthConfig, QPUConfig
from warden.lib.qpu_client.auth import (
    KeycloakClientCredentialsAuth,
    TokenRequestError,
)

TOKEN_URL = "http://keycloak:8080/realms/pasqos/protocol/openid-connect/token"
QPU_URL = "http://qpu:4300/api/v1/system"


@pytest.fixture
def auth_conf() -> QPUAuthConfig:
    return QPUAuthConfig(
        url="http://keycloak:8080", realm="pasqos", id="warden", secret="s3cret"
    )


@pytest.mark.asyncio
async def test_token_is_fetched_once_and_reused(httpx_mock: HTTPXMock, auth_conf):
    httpx_mock.add_response(
        url=TOKEN_URL,
        json={"access_token": "tok-1", "expires_in": 300},
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        first = await client.get(QPU_URL)
        second = await client.get(QPU_URL)

    assert first.request.headers["Authorization"] == "Bearer tok-1"
    assert second.request.headers["Authorization"] == "Bearer tok-1"
    token_requests = [r for r in httpx_mock.get_requests() if str(r.url) == TOKEN_URL]
    assert len(token_requests) == 1


@pytest.mark.asyncio
async def test_token_request_uses_client_credentials_grant(
    httpx_mock: HTTPXMock, auth_conf
):
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "tok-1", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        await client.get(QPU_URL)

    token_request = next(
        r for r in httpx_mock.get_requests() if str(r.url) == TOKEN_URL
    )
    body = token_request.read().decode()
    assert "grant_type=client_credentials" in body
    assert "client_id=warden" in body
    assert "client_secret=s3cret" in body


@pytest.mark.asyncio
async def test_expired_token_is_refreshed(
    httpx_mock: HTTPXMock, auth_conf, monkeypatch
):
    # expires_in 300 with leeway 30 means the token is stale after 270s.
    clock = {"now": 1_000.0}
    monkeypatch.setattr("warden.lib.qpu_client.auth.monotonic", lambda: clock["now"])
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "tok-1", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "tok-2", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        first = await client.get(QPU_URL)
        clock["now"] += 271
        second = await client.get(QPU_URL)

    assert first.request.headers["Authorization"] == "Bearer tok-1"
    assert second.request.headers["Authorization"] == "Bearer tok-2"


@pytest.mark.asyncio
async def test_401_triggers_one_refresh_and_one_retry(httpx_mock: HTTPXMock, auth_conf):
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "stale", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, status_code=401)
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "fresh", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        response = await client.get(QPU_URL)

    assert response.status_code == 200
    assert response.request.headers["Authorization"] == "Bearer fresh"
    qpu_requests = [r for r in httpx_mock.get_requests() if str(r.url) == QPU_URL]
    assert len(qpu_requests) == 2


@pytest.mark.asyncio
async def test_persistent_401_is_not_retried_forever(httpx_mock: HTTPXMock, auth_conf):
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "tok-1", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, status_code=401)
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "tok-2", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, status_code=401)

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        response = await client.get(QPU_URL)

    # The second 401 is surfaced, not retried again.
    assert response.status_code == 401
    qpu_requests = [r for r in httpx_mock.get_requests() if str(r.url) == QPU_URL]
    assert len(qpu_requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401])
async def test_bad_credentials_raise_token_request_error(
    httpx_mock: HTTPXMock, auth_conf, status_code
):
    httpx_mock.add_response(
        url=TOKEN_URL,
        status_code=status_code,
        json={"error": "invalid_client"},
    )

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        with pytest.raises(TokenRequestError, match="invalid_client"):
            await client.get(QPU_URL)


@pytest.mark.asyncio
async def test_keycloak_5xx_raises_retryable_http_status_error(
    httpx_mock: HTTPXMock, auth_conf
):
    # 503 must stay an httpx.HTTPStatusError so the existing retry decorator
    # recognises it as transient.
    httpx_mock.add_response(url=TOKEN_URL, status_code=503)

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        with pytest.raises(HTTPStatusError):
            await client.get(QPU_URL)


@pytest.mark.asyncio
async def test_async_flow_attaches_token(httpx_mock: HTTPXMock, auth_conf):
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "tok-async", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        response = await client.get(QPU_URL)

    assert response.request.headers["Authorization"] == "Bearer tok-async"


@pytest.mark.asyncio
async def test_short_lived_token_still_caches_with_warning(
    httpx_mock: HTTPXMock, auth_conf, caplog
):
    # expires_in 30 with the default leeway_s 30 would clamp to 0 without the
    # half-lifespan fallback, disabling the cache entirely and forcing a
    # Keycloak round-trip on every request.
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "tok-1", "expires_in": 30}
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    auth = KeycloakClientCredentialsAuth(auth_conf)
    with caplog.at_level(logging.WARNING, logger="warden.lib.qpu_client.auth"):
        async with AsyncClient(auth=auth) as client:
            await client.get(QPU_URL)
            await client.get(QPU_URL)

    token_requests = [r for r in httpx_mock.get_requests() if str(r.url) == TOKEN_URL]
    assert len(token_requests) == 1
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.asyncio
async def test_client_sends_no_authorization_header_without_auth_config(
    httpx_mock: HTTPXMock,
):
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    response = await QPUConfig(uri="http://qpu:4300").client.get(QPU_URL)

    assert "Authorization" not in response.request.headers


@pytest.mark.asyncio
async def test_401_on_post_retries_with_fresh_token_and_identical_body(
    httpx_mock: HTTPXMock, auth_conf
):
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "stale", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, status_code=401)
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": "fresh", "expires_in": 300}
    )
    httpx_mock.add_response(url=QPU_URL, json={"data": {}})

    body = {"circuit": "bell", "shots": 100}
    auth = KeycloakClientCredentialsAuth(auth_conf)
    async with AsyncClient(auth=auth) as client:
        response = await client.post(QPU_URL, json=body)

    assert response.status_code == 200
    assert response.request.headers["Authorization"] == "Bearer fresh"
    qpu_requests = [r for r in httpx_mock.get_requests() if str(r.url) == QPU_URL]
    assert len(qpu_requests) == 2
    for request in qpu_requests:
        assert json.loads(request.read()) == body
