"""Retry decorator for qpu_client"""

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


def retry(max_retry: int = 10, sleep_s: int = 0) -> Callable:
    """Return retry decorator for requests to PasqOS API"""

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            counter = 0

            current_err = ""
            while counter < max_retry:
                counter += 1
                try:
                    return func(*args, **kwargs)
                except (NetworkError, TimeoutException) as e:
                    current_err = e
                except HTTPStatusError as e:
                    if e.response.status_code not in RETRY_HTTP_EXIT_CODES:
                        raise NoRetryHTTPStatus(e)
                    current_err = e
                except Exception as e:
                    raise UnhandledError(e)
                time.sleep(sleep_s)
            raise MaxRetryError(current_err)

        return wrapper

    return decorator
