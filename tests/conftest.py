import os

import pytest

from tests.db_backend_config import build_database_config, config_backend_params
from tests.mock_qpu_api.app import create_app
from warden.lib.config.config import Config


@pytest.fixture(scope="function")
def mock_qpu_api_app():
    yield create_app()


@pytest.fixture(scope="function", params=config_backend_params())
def db_backend_config(request):
    """Function-scoped DB config for API tests (isolated sqlite file per test)."""
    return build_database_config(
        request.param,
        sqlite_path=(
            os.environ.get("SQLITE_MIGRATIONS_TEST_DB", "").strip()
            or "/tmp/scheduler.db"
        ),
    )


@pytest.fixture(scope="function")
def config_db(db_backend_config):
    yield Config(database=db_backend_config)
