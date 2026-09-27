"""Testing lib/config"""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from warden.lib.config.config import (
    APIConfig,
    Config,
    QPUAuthConfig,
    QPUConfig,
    SchedulerConfig,
    SchedulerStrategy,
    SqliteConfig,
)


def test_scheduler():
    assert Config().scheduler.strategy is SchedulerStrategy.FIFO

    with pytest.raises(ValidationError):
        SchedulerConfig(strategy=cast(Any, "NOT_FIFO"))


def test_config_env_vars_use_warden_prefix(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WARDEN_API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_HOST", "192.0.2.10")

    config = Config()

    assert config.api.host == "127.0.0.1"


def test_config_env_vars_nocase(monkeypatch, tmp_path):
    """
    Test that the parameters with underscores can be set by removing underscores
    in the env-variable alternative
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WARDEN_SCHEDULER_QPUPOLLINGINTERVALS", "999")
    monkeypatch.setenv("WARDEN_QPU_RETRYMAX", "999")
    monkeypatch.setenv("WARDEN_API_AUTHORIZEDUSERS", '[1001, "9999"]')

    config = Config()

    assert config.scheduler.qpu_polling_interval_s == 999
    assert config.qpu.retry_max == 999
    assert config.api.authorized_users == ["1001", "9999"]


def test_config_database_name_env_var_without_backend_defaults_to_sqlite(
    monkeypatch, tmp_path
):
    """
    Setting only WARDEN_DATABASE_NAME (no WARDEN_DATABASE_BACKEND), as done by
    some warden.mk targets, must not break discriminated-union validation.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WARDEN_DATABASE_NAME", "no_qpu.db")

    config = Config()

    assert config.database == SqliteConfig(name="no_qpu.db")


def test_config_parse_lists_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WARDEN_API_AUTHORIZEDUSERS", '[1001, "9999"]')
    monkeypatch.setenv("WARDEN_API_ADMINUSERS", '[1001, "9999"]')

    config = Config()

    assert config.api.authorized_users == ["1001", "9999"]
    assert config.api.admin_users == ["1001", "9999"]


def test_unprefixed_env_vars_do_not_override_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_HOST", "127.0.0.1")

    config = Config()

    assert config.api.host == "0.0.0.0"


def test_authorized_users():
    """
    Test that authorized_users is a list of strings
    coerced from user inputs
    """
    config = APIConfig(authorized_users=cast(Any, [1000, "2000"]))
    assert "1000" in config.authorized_users
    assert "2000" in config.authorized_users
    assert 1000 not in config.authorized_users


def test_authorized_users_wrong_input():
    """
    Test that authorized_users is a list of strings
    coerced from user inputs that must be either strings or integers

    1. Test list input error
    2. Test float input error
    """
    with pytest.raises(ValidationError):
        APIConfig(authorized_users=cast(Any, [[]]))

    with pytest.raises(ValidationError):
        APIConfig(authorized_users=cast(Any, [1.0]))

    with pytest.raises(ValidationError):
        APIConfig(authorized_users=cast(Any, "1000"))


def test_admin_users_default():
    config = APIConfig()
    assert config.admin_users == ["0"]


def test_admin_users():
    """
    Test that admin_users is a list of strings
    coerced from user inputs
    """
    config = APIConfig(admin_users=cast(Any, [0, "1001"]))
    assert "0" in config.admin_users
    assert "1001" in config.admin_users
    assert 0 not in config.admin_users


def test_admin_users_wrong_input():
    """
    Test that admin_users is a list of strings
    coerced from user inputs that must be either strings or integers
    """
    with pytest.raises(ValidationError):
        APIConfig(admin_users=cast(Any, [[]]))

    with pytest.raises(ValidationError):
        APIConfig(admin_users=cast(Any, [1.0]))

    with pytest.raises(ValidationError):
        APIConfig(admin_users=cast(Any, "1000"))


def test_admin_users_must_not_be_empty():
    """
    admin_users must list at least one uid (e.g. the user running the spank
    plugin), otherwise Warden cannot create sessions on behalf of users.
    """
    with pytest.raises(ValidationError):
        APIConfig(admin_users=[])


def test_qpu_auth_absent_by_default():
    assert Config().qpu.auth is None


def test_qpu_auth_token_url_is_built_from_base_and_realm():
    auth = QPUAuthConfig(
        url="http://keycloak:8080", realm="pasqos", id="warden", secret="s"
    )

    assert (
        auth.token_url
        == "http://keycloak:8080/realms/pasqos/protocol/openid-connect/token"
    )


def test_qpu_auth_token_url_tolerates_trailing_slash():
    auth = QPUAuthConfig(
        url="http://keycloak:8080/", realm="pasqos", id="warden", secret="s"
    )

    assert (
        auth.token_url
        == "http://keycloak:8080/realms/pasqos/protocol/openid-connect/token"
    )


def test_qpu_auth_rejects_partial_configuration():
    # A half-configured auth section must fail loudly rather than silently
    # falling back to unauthenticated requests.
    with pytest.raises(ValidationError):
        # model_validate, not the constructor: omitting a required field is the
        # point of the test, and a static type checker rejects the direct call.
        QPUAuthConfig.model_validate({"url": "http://keycloak:8080", "id": "warden"})


def test_qpu_auth_secret_read_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WARDEN_QPU_AUTH_URL", "http://keycloak:8080")
    monkeypatch.setenv("WARDEN_QPU_AUTH_ID", "warden")
    monkeypatch.setenv("WARDEN_QPU_AUTH_SECRET", "from-env")

    config = Config()

    assert config.qpu.auth is not None
    assert config.qpu.auth.id == "warden"
    assert config.qpu.auth.secret == "from-env"


def test_auth_flow_is_none_without_auth_config():
    assert Config().qpu.auth_flow is None


def test_auth_flow_is_memoized():
    qpu = QPUConfig(
        uri="http://qpu:4300",
        auth=QPUAuthConfig(url="http://keycloak:8080", id="warden", secret="s"),
    )

    assert qpu.auth_flow is qpu.auth_flow


def test_client_is_given_the_auth_flow():
    qpu = QPUConfig(
        uri="http://qpu:4300",
        auth=QPUAuthConfig(url="http://keycloak:8080", id="warden", secret="s"),
    )

    assert qpu.client.auth is qpu.auth_flow


def test_client_has_no_auth_without_auth_config():
    assert QPUConfig(uri="http://qpu:4300").client.auth is None
