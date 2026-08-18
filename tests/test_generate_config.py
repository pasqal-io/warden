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
from warden.lib.config.generate_config import (
    SECTION_DESCRIPTIONS,
    generate_config,
    main,
)

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


def test_generate_config_documents_every_section():
    """Test that every section has a description comment right above its header"""
    generated = generate_config()

    for section, description in SECTION_DESCRIPTIONS.items():
        assert f"# {description}\n{section}:" in generated


def test_generate_config_documents_every_field():
    """Test that all the fields are documented in the generated config file"""
    generated = generate_config()

    for name in ALL_FIELD_NAMES:
        assert f"# {name}:" in generated


def test_generate_config_preserves_existing_overrides():
    """Test that values already set in a previous config.yaml stay uncommented
    below their commented-out default, while untouched fields only keep
    documenting their default, commented out"""
    existing = {
        "api": {"host": "127.0.0.1"},
        "database": {
            "backend": "postgres",
            "host": "db.internal",
            "user": "wardenuser",
            "password": "secret",
        },
    }

    generated = generate_config(existing)

    # The default stays commented, right above the overridden value.
    assert "  # host: 0.0.0.0\n  host: 127.0.0.1" in generated
    assert "  # backend: sqlite\n  backend: postgres" in generated
    assert "  host: db.internal" in generated
    assert "  user: wardenuser" in generated
    assert "  password: secret" in generated
    # Untouched fields still document their default, commented out.
    assert "  # port: 8006" in generated
    assert "  # echo: false" in generated


def test_main_writes_directly_when_no_previous_file(tmp_path):
    """Test that main() writes the file without creating a backup on first run"""
    output_path = tmp_path / "config.yaml"

    main([str(output_path)])

    assert output_path.exists()
    assert not (tmp_path / "config.backup-1.yaml").exists()


def test_main_preserves_overrides_and_backs_up_previous_file(tmp_path):
    """Test that main() merges overrides from, and backs up, its target file"""
    output_path = tmp_path / "config.yaml"
    output_path.write_text("api:\n  host: 127.0.0.1\n")

    main([str(output_path)])

    assert "  host: 127.0.0.1" in output_path.read_text()
    assert (
        tmp_path / "config.backup-1.yaml"
    ).read_text() == "api:\n  host: 127.0.0.1\n"


def test_main_is_a_noop_when_nothing_changed(tmp_path):
    """Test that re-running main() on an already up-to-date file creates no backup"""
    output_path = tmp_path / "config.yaml"
    main([str(output_path)])
    generated = output_path.read_text()

    main([str(output_path)])

    assert output_path.read_text() == generated
    assert not (tmp_path / "config.backup-1.yaml").exists()


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
