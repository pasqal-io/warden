"""Retry decorator for qpu_client"""

import asyncio
from functools import wraps
from typing import Callable

from httpx2 import HTTPStatusError, NetworkError, TimeoutException

RETRY_HTTP_EXIT_CODES = [500, 502, 503, 504, 429]


class QPUClientRequestError(Exception):
    pass


class UnhandledError(QPUClientRequestError):
    pass


class NotRetriedHTTPStatus(QPUClientRequestError):
    def __init__(self, http_status_error: HTTPStatusError):
        self.response = http_status_error.response
        self.request = http_status_error.request
        message = (
            f"Caught not-retryable http status code: '{http_status_error.response.status_code}' "
            f"error for request '{http_status_error.request}'."
        )
        super().__init__(message)


class MaxRetryError(QPUClientRequestError):
    def __init__(self, last_error: Exception):
        request = getattr(last_error, "request", "<unknown>")
        message = (
            f"Max retry error for request '{request}', last error: '{last_error}'."
        )
        super().__init__(message)


def retry(max: int, sleep_s: float, no_retry: bool = False) -> Callable:
    """
    Return retry decorator for requests to QPU API with HTTPX client

    Args:
        max (int): Max number of retry attempts.
        sleep_s (float): Time sleep between retries.
        no_retry (bool): Disables the retry loop. Defaults to False

    Raises:
        UnhandledError: If decorator encounters an unnexpected exception.
        NotRetriedHTTPStatus: If the HTTP request returns with a non-retryable error code.
        MaxRetryError: If the maximum number of retries without success has been reached.
        QPUClientRequestError: If `no_retry=True` or any subclass already classified as
            non-retryable by the wrapped function (e.g. TokenRequestError) propagates unchanged.
    """

    def decorator(func: Callable):

        def _handle_exception(e: Exception):
            if isinstance(e, (NetworkError, TimeoutException)):
                pass
            elif isinstance(e, HTTPStatusError):
                if e.response.status_code not in RETRY_HTTP_EXIT_CODES:
                    raise NotRetriedHTTPStatus(e) from e
            elif isinstance(e, QPUClientRequestError):
                # Already classified as non-retryable by the raiser (e.g. bad
                # Keycloak credentials). Do not rewrap it as UnhandledError.
                raise
            else:
                raise UnhandledError(e) from e

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 1
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if no_retry:
                        raise QPUClientRequestError(e) from e
                    if attempt >= max:
                        raise MaxRetryError(e) from e
                    _handle_exception(e)
                await asyncio.sleep(sleep_s)
                attempt += 1

        return async_wrapper

    return decorator
