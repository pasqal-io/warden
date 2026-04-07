import pytest
from mock_qpu_api.app import create_app


@pytest.fixture(scope="session")
def mock_qpu_api_app():
    yield create_app()
