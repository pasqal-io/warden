import os

import pytest

from tests.db_backend_config import build_database_config, config_backend_params
from tests.mock_qpu_api.app import create_app
from warden.lib.config.config import Config


@pytest.fixture(scope="session")
def mock_qpu_api_app():
    # Set shot duration to 0 for quick qpu api behavior
    os.environ["MOCK_QPU_API_SHOT_DURATION_S"] = "0"
    yield create_app()
    os.unsetenv("MOCK_QPU_API_SHOT_DURATION_S")


@pytest.fixture(scope="session", params=config_backend_params())
def db_backend_config(request):
    """Function-scoped DB config for tests."""
    return build_database_config(
        request.param,
    )


@pytest.fixture(scope="session")
def config_db(db_backend_config):
    yield Config(database=db_backend_config)
