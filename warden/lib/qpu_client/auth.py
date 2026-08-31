"""Keycloak client_credentials authentication for outbound QPU API calls."""

import logging
import ssl
from time import monotonic
from typing import AsyncGenerator, Generator

import httpx2

from warden.lib.config.config import QPUAuthConfig
from warden.lib.qpu_client.retry import QPUClientRequestError

logger = logging.getLogger(__name__)

# Token-endpoint statuses that will never succeed on retry: the credentials or
# the grant itself are wrong. Anything else (transport errors, 5xx) is left to
# propagate so the existing retry decorator can treat it as transient.
FATAL_TOKEN_STATUSES = (400, 401, 403)


class TokenRequestError(QPUClientRequestError):
    """Keycloak refused to issue a token and retrying cannot help."""


class KeycloakClientCredentialsAuth(httpx2.Auth):
    """Attach a Keycloak service-account bearer token to each request.

    Implemented as an ``httpx.Auth`` so it runs inside the transport, below
    Warden's ``retry`` decorator. That matters because 401 is not in
    ``RETRY_HTTP_EXIT_CODES``: a token expiring mid-job would otherwise surface
    as an immediate, non-retryable ``NotRetriedHTTPStatus``. Here it is just a
    refresh.

    Args:
        conf: Keycloak credentials and endpoint.
        verify: httpx TLS verification setting for the token request.
    """

    def __init__(
        self,
        conf: QPUAuthConfig,
        verify: bool | str | ssl.SSLContext = True,
    ) -> None:
        self.conf = conf
        self.verify = verify
        self._token: str | None = None
        # monotonic() deadline after which the cached token is considered stale.
        self._expires_at: float = 0.0

    def sync_auth_flow(
        self, request: httpx2.Request
    ) -> Generator[httpx2.Request, httpx2.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._sync_token()}"
        response = yield request
        if response.status_code == httpx2.codes.UNAUTHORIZED:
            logger.info("QPU API returned 401, refreshing token and retrying once")
            request.headers["Authorization"] = f"Bearer {self._sync_token(force=True)}"
            yield request

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        request.headers["Authorization"] = f"Bearer {await self._async_token()}"
        response = yield request
        if response.status_code == httpx2.codes.UNAUTHORIZED:
            logger.info("QPU API returned 401, refreshing token and retrying once")
            request.headers["Authorization"] = (
                f"Bearer {await self._async_token(force=True)}"
            )
            yield request

    def _is_fresh(self) -> bool:
        return self._token is not None and monotonic() < self._expires_at

    def _token_request(self) -> tuple[str, dict[str, str]]:
        """Return the (url, form data) for a client_credentials token request."""
        return self.conf.token_url, {
            "grant_type": "client_credentials",
            "client_id": self.conf.id,
            "client_secret": self.conf.secret,
        }

    def _store(self, response: httpx2.Response) -> str:
        """Validate a token response, cache the token and return it."""
        if response.status_code in FATAL_TOKEN_STATUSES:
            # Never log the response body of a token request: it may echo
            # credentials. The error field alone is the useful part.
            try:
                error = response.json().get("error", "unknown_error")
            except (ValueError, AttributeError):
                error = "unknown_error"
            raise TokenRequestError(
                f"Keycloak refused to issue a token for client "
                f"'{self.conf.id}' at {self.conf.token_url}: "
                f"{response.status_code} {error}"
            )
        # Transport errors and 5xx stay as httpx exceptions so the existing
        # retry decorator sees them as transient.
        response.raise_for_status()

        payload = response.json()
        token = payload["access_token"]
        expires_in = float(payload.get("expires_in", 0))
        self._token = token
        configured_ttl = expires_in - self.conf.leeway_s
        ttl = max(configured_ttl, expires_in / 2)
        if ttl > configured_ttl:
            logger.warning(
                f"Configured leeway {self.conf.leeway_s}s leaves less than "
                f"half of the {expires_in}s token lifespan; caching for "
                f"{ttl}s (half the lifespan) instead."
            )
        self._expires_at = monotonic() + ttl
        logger.debug(
            f"Obtained QPU API token for client '{self.conf.id}', "
            f"expires in {expires_in}s"
        )
        return token

    def _sync_token(self, force: bool = False) -> str:
        if not force and self._is_fresh():
            assert self._token is not None
            return self._token
        url, data = self._token_request()
        with httpx2.Client(verify=self.verify) as client:
            return self._store(client.post(url, data=data))

    # Note: unlocked check-then-fetch. Two concurrent async requests in one
    # process can both miss and both fetch a token; one wins and the loser
    # wasted a request. The sync path (scheduler) blocks its single event loop
    # per fetch, so this race is only reachable via awaited callers here. Add
    # a lock only if token-endpoint traffic ever becomes a problem.
    async def _async_token(self, force: bool = False) -> str:
        if not force and self._is_fresh():
            assert self._token is not None
            return self._token
        url, data = self._token_request()
        async with httpx2.AsyncClient(verify=self.verify) as client:
            return self._store(await client.post(url, data=data))
