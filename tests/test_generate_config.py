"""Testing lib/config/generate_config"""

import yaml

from warden.lib.config.config import (
    APIConfig,
    Config,
    MariadbConfig,
    PostgresConfig,
    QPUConfig,
    SchedulerConfig,
    SqliteConfig,
)
from warden.lib.config.generate_config import generate_config

ALL_FIELD_NAMES = {
    name
    for model in (
        APIConfig,
        SchedulerConfig,
        QPUConfig,
        SqliteConfig,
        PostgresConfig,
        MariadbConfig,
    )
    for name in model.model_fields
}


def test_generate_config_is_valid_yaml():
    """Test that all the sections are correctly generated"""
    generated = generate_config()

    data = yaml.safe_load(generated)

    assert set(data) == {"api", "database", "scheduler", "qpu", "logging"}


def test_generate_config_documents_every_field():
    """Test that all the fields are documented in the generated config file"""
    generated = generate_config()

    for name in ALL_FIELD_NAMES:
        assert f"# {name}:" in generated


def test_generate_config_round_trips_to_defaults(monkeypatch, tmp_path):
    # Every field is commented out, so this should behave like no config.yaml at
    # all -- except `logging:`, which has no in-code default and is always active.
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    expected = Config().model_dump()
    del expected["logging"]

    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    (generated_dir / "config.yaml").write_text(generate_config())
    monkeypatch.chdir(generated_dir)
    actual = Config().model_dump()

    assert actual["logging"]
    del actual["logging"]
    assert actual == expected
