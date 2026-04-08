"""Retry decorator for qpu_client"""

import asyncio
import inspect
import time
from functools import wraps
from typing import Callable

from httpx import HTTPError, HTTPStatusError, NetworkError, TimeoutException

RETRY_HTTP_EXIT_CODES = [500, 502, 503, 504, 429]


class QPUClientRequestError(Exception):
    pass


class UnhandledError(QPUClientRequestError):
    pass


class NoRetryHTTPStatus(QPUClientRequestError):
    def __init__(self, http_status_error: HTTPStatusError):
        self.response = http_status_error.response
        self.request = http_status_error.request
        message = (
            f"Caught not-retryable http status code: '{http_status_error.response.status_code}' "
            f"error for request '{http_status_error.request}'."
        )
        super().__init__(message)


class MaxRetryError(QPUClientRequestError):
    def __init__(self, last_error: HTTPError):
        message = (
            f"Max retry error for request '{last_error.request}', "
            f"last error: '{last_error}'."
        )
        super().__init__(message)


def retry(max: int, sleep_s: float, no_retry: bool = False) -> Callable:
    """
    Return retry decorator for requests to PasqOS API with HTTPX client

    Args:
        max (int): Max number of retry attempts.
        sleep_s (float): Time sleep between retries.
        no_retry (bool): Disables the retry loop. Defaults to False

    Raises:
        UnhandledError: If decorator encounters an unnexpected exception.
        NoRetryHTTPStatus: If the HTTP request returns with a non-retryable error code.
        MaxRetryError: If the maximum number of retries without success has been reached.
    """

    def decorator(func: Callable):

        def _handle_exception(e: Exception, attempt: int):
            if isinstance(e, (NetworkError, TimeoutException)):
                pass
            elif isinstance(e, HTTPStatusError):
                if e.response.status_code not in RETRY_HTTP_EXIT_CODES:
                    raise NoRetryHTTPStatus(e)
            else:
                raise UnhandledError(e)

            if no_retry:
                raise QPUClientRequestError(e)

            if attempt >= max:
                raise MaxRetryError(e)

        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    _handle_exception(e, attempt)
                time.sleep(sleep_s)
                attempt += 1

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 1
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    _handle_exception(e, attempt)
                await asyncio.sleep(sleep_s)
                attempt += 1

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
