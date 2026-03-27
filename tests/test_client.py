"""Testing warden.lib.qpu_client"""

import httpx

import pytest
import pytest_httpx
from pytest_httpx import HTTPXMock

from warden.lib.qpu_client import QPUClient

def test_qpu_retry(httpx_mock: HTTPXMock):

    httpx_mock.add_exception(httpx.ConnectError("Connection error"))
    httpx_mock.add_exception(httpx.ConnectTimeout())

