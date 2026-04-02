import pytest
from mock_pasqos_api.app import create_app


@pytest.fixture(scope="session")
def mock_api_app():
    yield create_app()
