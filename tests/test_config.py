"""Testing lib/config"""

import pytest
from pydantic import ValidationError

from warden.lib.config.config import Config, SchedulerConfig


def test_scheduler_config():
    with pytest.raises(ValidationError):
        SchedulerConfig(strategy="NOT_FIFO", db_polling_interval_s=1)


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
