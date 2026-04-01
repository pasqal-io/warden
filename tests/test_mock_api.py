"""Testing mock api's"""

import pytest
from fastapi.testclient import TestClient
from mock_api.app import create_app

from warden.lib.qpu_client import QPUClient

BASE_URI = "http://test:4300/api/v1"


@pytest.fixture
def mock_api_client():
    # The fastapi TestClient is based on the httpx client and should
    # have the same behavior
    # https://fastapi.tiangolo.com/tutorial/testing/
    with TestClient(app=create_app(), base_url=BASE_URI) as client:
        yield client


def test_get_qpu_status(mock_api_client):
    """Test nominal get qpu status api call"""

    qpu_client = QPUClient(base_uri="any")
    qpu_client.client = mock_api_client

    qpu_status = qpu_client.get_operational_status()

    assert qpu_status == "UP"
