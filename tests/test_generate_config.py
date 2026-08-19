"""Testing lib/config/generate_config"""

import yaml
from pydantic import BaseModel, Field

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
    _render_fields,
    generate,
    generate_config,
    migrate,
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


def test_generate_config_documents_every_field():
    """Test that all the fields are documented in the generated config file"""
    generated = generate_config()

    for name in ALL_FIELD_NAMES:
        assert f"# {name}:" in generated


def test_generate_config_preserves_existing_overrides():
    """Test that values already set in a previous config.yaml stay uncommented
    below their commented-out default, while untouched fields only keep
    documenting their default, commented out"""
    existing_data = {
        "api": {"host": "127.0.0.1"},
        "database": {
            "backend": "postgres",
            "host": "db.internal",
            "user": "wardenuser",
            "password": "secret",
        },
    }

    generated = generate_config(existing_data)

    generated_data = yaml.safe_load(generated)

    # Assert existing_data is replicated in generated_data
    assert existing_data == {key: generated_data[key] for key in existing_data.keys()}

    # The default stays commented, right above the overridden value.
    assert "  # host: " in generated
    assert "  # backend: " in generated
    # Untouched fields still document their default, commented out.
    assert "  # port: " in generated
    assert "  # echo: " in generated


def test_render_fields_indents_nested_models():
    """Test that a field whose type is itself a model is rendered as its own
    nested block, indented one level deeper, with overrides merged the same
    way as flat fields"""

    class Inner(BaseModel):
        value: int = Field(default=1, description="An inner value.")

    class Outer(BaseModel):
        inner: Inner = Field(default=Inner(), description="Nested block.")
        flat: str = Field(default="x", description="A flat field.")

    generated = _render_fields(Outer.model_fields, {}, 1)

    assert "  inner:\n    # An inner value.\n    # value: 1" in generated
    assert "  # flat: x" in generated
    # Both defaults are commented out, so nothing is actually set.
    assert yaml.safe_load(f"outer:\n{generated}") == {"outer": {"inner": None}}

    overridden = _render_fields(Outer.model_fields, {"inner": {"value": 42}}, 1)

    assert "    value: 42" in overridden
    assert yaml.safe_load(f"outer:\n{overridden}") == {
        "outer": {"inner": {"value": 42}}
    }


def test_generate_writes_directly_when_no_previous_file(tmp_path, monkeypatch):
    """Test that generate() writes the file without creating a backup on first run"""
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "config.yaml"

    generate()

    assert output_path.exists()
    assert not (tmp_path / "config.backup-1.yaml").exists()


def test_generate_backs_up_and_overwrites_previous_file(tmp_path, monkeypatch):
    """Test that generate() discards previous values, backing up the
    replaced file rather than preserving its overrides"""
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "config.yaml"
    output_path.write_text("api:\n  host: 127.0.0.1\n")

    generate()

    assert "127.0.0.1" not in output_path.read_text()
    assert (
        tmp_path / "config.backup-1.yaml"
    ).read_text() == "api:\n  host: 127.0.0.1\n"


def test_generate_is_a_noop_when_nothing_changed(tmp_path, monkeypatch):
    """Test that re-running generate() on an already up-to-date file creates
    no backup"""
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "config.yaml"
    generate()
    generated = output_path.read_text()

    generate()

    assert output_path.read_text() == generated
    assert not (tmp_path / "config.backup-1.yaml").exists()


def test_migrate_keeps_previous_logging_section_verbatim(tmp_path, monkeypatch):
    """Test that a previously set-up logging: section is kept as-is, comments
    and all, instead of being replaced by the model's default logging config"""
    monkeypatch.chdir(tmp_path)
    custom_logging = (
        "logging:\n"
        "  version: 1\n"
        "  loggers:\n"
        "    warden:\n"
        "      level: DEBUG  # noisier for local debugging\n"
    )
    output_path = tmp_path / "config.yaml"
    output_path.write_text(custom_logging)

    migrate()

    assert output_path.read_text().endswith(custom_logging)


def test_migrate_preserves_overrides_and_backs_up_previous_file(tmp_path, monkeypatch):
    """Test that migrate() merges overrides from, and backs up, its target file"""
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "config.yaml"
    output_path.write_text("api:\n  host: 127.0.0.1\n")

    migrate()

    assert "  host: 127.0.0.1" in output_path.read_text()
    assert (
        tmp_path / "config.backup-1.yaml"
    ).read_text() == "api:\n  host: 127.0.0.1\n"


def test_migrate_is_a_noop_when_nothing_changed(tmp_path, monkeypatch):
    """Test that re-running migrate() on an already up-to-date file creates no backup"""
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "config.yaml"
    generate()
    generated = output_path.read_text()

    migrate()

    assert output_path.read_text() == generated
    assert not (tmp_path / "config.backup-1.yaml").exists()


def test_generate_config_round_trips_to_defaults(monkeypatch, tmp_path):
    # Every field is commented out, so this should behave like no config.yaml at
    # all except logging, which is always active.
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


def test_ignore_invalid_config(tmp_path, monkeypatch):
    """Test that an invalid pre-existing configuration file is ignored"""
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "config.yaml"

    # Generate a valid config and add non-valid data in it
    output_path.write_text("api:\n  host: 127.0.0.9\n\nNonesense")

    # Migrate the existing configuration file
    migrate()

    # Verify that the generated config.yaml ignored previously set values
    conf = Config()
    assert conf.api.host != "127.0.0.9"
