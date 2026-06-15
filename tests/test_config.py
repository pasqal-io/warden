"""Testing lib/config"""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from warden.lib.config.config import (
    APIConfig,
    Config,
    SchedulerConfig,
    SchedulerStrategy,
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
