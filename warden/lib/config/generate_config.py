"""
Utility script to generate config.yaml from config.py's field defaults and descriptions.
"""

import re
import sys
import textwrap
from enum import Enum
from pathlib import Path

import yaml
from pydantic import AliasChoices, BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from warden.lib.config.config import (
    CONFIG_FILENAME,
    DEFAULT_LOGGING_CONFIG,
    APIConfig,
    Config,
    MariadbConfig,
    PostgresConfig,
    QPUConfig,
    SchedulerConfig,
    SqliteConfig,
)

HEADER = """\
# Example configuration for Warden. Every key below is commented out and
# shows the built-in default. Uncomment only the keys you want to override."""

# logging is a free-form dict (not a modeled field per key), so it can't be
# rendered field-by-field like the other sections: it's always dumped in
# full, active (uncommented) form, either from the previous config.yaml
# verbatim (see _existing_logging_section) or from the model's own default.
LOGGING_SECTION = yaml.safe_dump(
    {"logging": DEFAULT_LOGGING_CONFIG}, sort_keys=False
).rstrip("\n")

SECTION_MODELS = {
    "api": APIConfig,
    "scheduler": SchedulerConfig,
    "qpu": QPUConfig,
}
# Discriminated union of database backends: rendered as the union of their
# fields, each documented once using the first backend (in this order) that
# declares it.
DATABASE_MODELS = [SqliteConfig, PostgresConfig, MariadbConfig]

# Section order in the generated file.
SECTIONS = ["api", "database", "scheduler", "qpu", "logging"]

SECTION_DESCRIPTIONS = {
    # api/scheduler/qpu map 1:1 to a model, so their description is the
    # model's own docstring. database (a 3-way backend union) and logging
    # (untyped, free-form dictConfig) don't map to a single model, so their
    # description is declared here instead.
    **{section: model.__doc__ for section, model in SECTION_MODELS.items()},
    "database": "Database backend configuration. Warden supports SQLite, PostgreSQL and MariaDB.",
    "logging": "Logging configuration (Python dictConfig format).",
}

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
LOGGING_HEADER_RE = re.compile(r"^logging:\s*$", re.MULTILINE)
COMMENT_WIDTH = 88
# 2-space indent
INDENT_UNIT = "  "


def _yaml_scalar(value) -> str:
    if isinstance(value, Enum):
        value = value.value
    # First line only: safe_dump appends a "...\n" document-end marker after
    # bare scalars (but not after flow-style collections).
    # default_flow_style allows for a more compact json-like style
    return yaml.safe_dump(value, default_flow_style=True).splitlines()[0]


def _wrap_indented_text(text: str, indent: str) -> list[str]:
    """Wrap text around the max COMMENT_WIDTH"""
    prefix = f"{indent}# "
    return textwrap.wrap(
        text, width=COMMENT_WIDTH, initial_indent=prefix, subsequent_indent=prefix
    )


def _get_nested_model(field: FieldInfo) -> type[BaseModel] | None:
    """Returns if the field type is indeed a BaseModel subclass"""
    field_annotation = field.annotation
    if isinstance(field_annotation, type) and issubclass(field_annotation, BaseModel):
        return field_annotation
    return None


def _potential_field_aliases(field_name: str, field_info: FieldInfo) -> list[str]:
    """Look through the fields_info for potential aliases"""
    keys = [field_name]
    alias = field_info.validation_alias
    if isinstance(alias, str):
        candidates = [alias]
    elif isinstance(alias, AliasChoices):
        candidates = [c for c in alias.choices if isinstance(c, str)]
    else:
        candidates = []  # AliasPath (nested lookup) doesn't apply here.
    keys.extend(key for key in candidates if key not in keys)
    return keys


def _existing_value(
    previous_section_data: dict, field_name: str, field_info: FieldInfo
):
    """Get the preivously setup data for this field, looks through aliases also"""
    for key in _potential_field_aliases(field_name, field_info):
        value = previous_section_data.get(key)
        if value is not None:
            return value
    return None


def _render_field(
    name: str, field_info: FieldInfo, previous_section_data: dict, depth: int
) -> str:
    """
    Renders the pydantic field. Adds corresponding comments and keeps previously set value
    """

    indent = INDENT_UNIT * depth

    # Add comment lines
    lines = [
        wrapped
        for paragraph in (field_info.description or "").split("\n")
        if paragraph
        for sentence in SENTENCE_RE.split(paragraph)
        if sentence
        for wrapped in _wrap_indented_text(sentence, indent)
    ]

    # Get matching previously set data that we need to migrate to new config
    data_to_migrate = _existing_value(previous_section_data, name, field_info)

    # Check if contains a nested model and recursively renders it
    nested_model = _get_nested_model(field_info)
    if nested_model is not None:
        nested_existing = data_to_migrate if isinstance(data_to_migrate, dict) else {}
        lines.append(f"{indent}{name}:")
        lines.append(
            _render_section_fields(
                nested_model.model_fields, nested_existing, depth + 1
            )
        )
        return "\n".join(lines)

    # Add default value and previously set value to migrate
    if field_info.default is PydanticUndefined:
        lines.append(f"{indent}# {name}: ...  # required, no default")
    else:
        lines.append(f"{indent}# {name}: {_yaml_scalar(field_info.default)}")
    if data_to_migrate is not None:
        # Keep the value the user already set, uncommented, below its default.
        lines.append(f"{indent}{name}: {_yaml_scalar(data_to_migrate)}")
    return "\n".join(lines)


def _render_section_fields(
    fields: dict[str, FieldInfo], previous_section_data: dict, depth: int
) -> str:
    return "\n\n".join(
        _render_field(field_name, field_info, previous_section_data, depth)
        for field_name, field_info in fields.items()
    )


def _database_fields() -> dict[str, FieldInfo]:
    fields: dict[str, FieldInfo] = {}
    for model in DATABASE_MODELS:
        for name, field in model.model_fields.items():
            fields.setdefault(name, field)
    return fields


def _existing_logging_section(existing_text: str | None) -> str | None:
    # logging has no in-code schema, so a previously set-up section is kept
    # as-is (comments and all) rather than regenerated from LOGGING_SECTION.
    if not existing_text:
        return None
    match = LOGGING_HEADER_RE.search(existing_text)
    if not match:
        return None
    return existing_text[match.start() :].rstrip("\n") or None


def generate_config(
    previous_data: dict | None = None, previous_text: str | None = None
) -> str:
    """Generate a new config from model definition and eventual previous fields set"""
    previous_data = previous_data or {}

    blocks = [HEADER]
    for section in SECTIONS:
        header = f"# {SECTION_DESCRIPTIONS[section]}\n"
        if section == "logging":
            blocks.append(
                header + (_existing_logging_section(previous_text) or LOGGING_SECTION)
            )
        elif section == "database":
            blocks.append(
                header
                + "database:\n"
                + _render_section_fields(
                    _database_fields(), previous_data.get("database") or {}, 1
                )
            )
        else:
            blocks.append(
                header
                + f"{section}:\n"
                + _render_section_fields(
                    SECTION_MODELS[section].model_fields,
                    previous_data.get(section) or {},
                    1,
                )
            )

    return "\n\n".join(blocks) + "\n"


def _backup(path: Path, content: str) -> None:
    # Skip if the most recent backup already holds this exact content.
    i = 1
    last_backup = None
    while (
        candidate := path.with_name(f"{path.stem}.backup-{i}{path.suffix}")
    ).exists():
        last_backup = candidate
        i += 1
    if last_backup is None or last_backup.read_text() != content:
        path.with_name(f"{path.stem}.backup-{i}{path.suffix}").write_text(content)


def generate() -> None:
    """Write a fresh config.yaml from the model defaults, discarding any
    values set in a previous file but keeping a backup of it (use migrate()
    to update an existing file while preserving its values instead)."""
    output_path = Path.cwd() / CONFIG_FILENAME
    content = generate_config()

    previous_text = output_path.read_text() if output_path.exists() else None
    if content == previous_text:
        return

    if previous_text is not None:
        _backup(output_path, previous_text)
    output_path.write_text(content)


def migrate() -> None:
    """Regenerate config.yaml, preserving values already set in the previous
    file, and back it up if it changes."""
    output_path = Path.cwd() / CONFIG_FILENAME

    previous_text = output_path.read_text() if output_path.exists() else None
    previous_data = None
    if previous_text:
        try:
            Config()
            loaded = yaml.safe_load(previous_text)
            previous_data = loaded
        except (yaml.YAMLError, ValidationError):
            print("Previous config.yaml is not valid YAML/Config: ignore it.")

    content = generate_config(previous_data, previous_text)
    if content == previous_text:
        return

    if previous_text is not None:
        _backup(output_path, previous_text)
    output_path.write_text(content)


if __name__ == "__main__":
    migrate() if "--migrate" in sys.argv[1:] else generate()
