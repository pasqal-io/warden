"""Generate config.yaml from config.py's field defaults and descriptions."""

import re
import sys
import textwrap
from enum import Enum
from pathlib import Path

import yaml
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from warden.lib.config.config import (
    APIConfig,
    MariadbConfig,
    PostgresConfig,
    QPUConfig,
    SchedulerConfig,
    SqliteConfig,
)

HEADER = """\
# Example configuration for Warden. Every key below is commented out and
# shows the built-in default -- copy this file to config.yaml and uncomment
# only the keys you want to override.
# (except `logging:`, which has no in-code default and is always active)"""

# `logging:` has no in-code default (it's free-form dictConfig) and is always
# active, so it's kept as a static template rather than derived from a schema.
LOGGING_SECTION = """\
logging:
  version: 1
  disable_existing_loggers: false

  root:
    handlers:
      - console
      - file

  loggers:
    warden:
      level: INFO
      handlers: [console, file]
      propagate: false
    uvicorn:
      level: INFO
      handlers: [console, file]
      propagate: false
    uvicorn.error:
      level: INFO
      handlers: [console, file]
      propagate: false
    uvicorn.access:
      level: INFO
      handlers: [console, file]
      propagate: false

  handlers:
    console:
      class: logging.StreamHandler
      stream: "ext://sys.stderr"
      formatter: default
    file:
      class: logging.handlers.RotatingFileHandler
      filename: "logs/warden.log"
      maxBytes: 10485760 # 10MB
      backupCount: 5
      encoding: "utf-8"
      formatter: default

  formatters:
    default:
      format: "[%(asctime)s] %(levelname)s %(name)s: %(message)s\""""

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
    "logging": "Logging configuration (Python dictConfig format). Always active, has no in-code default.",
}

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
COMMENT_WIDTH = 88


def _yaml_scalar(value) -> str:
    if isinstance(value, Enum):
        value = value.value
    # First line only: safe_dump appends a "...\n" document-end marker after
    # bare scalars (but not after flow-style collections).
    return yaml.safe_dump(value, default_flow_style=True).splitlines()[0]


def _wrap_comment(text: str) -> list[str]:
    return textwrap.wrap(
        text, width=COMMENT_WIDTH, initial_indent="  # ", subsequent_indent="  # "
    )


def _render_field(name: str, field: FieldInfo, existing_value=None) -> str:
    lines = [
        wrapped
        for paragraph in (field.description or "").split("\n")
        if paragraph
        for sentence in SENTENCE_RE.split(paragraph)
        if sentence
        for wrapped in _wrap_comment(sentence)
    ]
    if field.default is PydanticUndefined:
        lines.append(f"  # {name}: ...  # required, no default")
    else:
        lines.append(f"  # {name}: {_yaml_scalar(field.default)}")
    if existing_value is not None:
        # Keep the value the user already set, uncommented, below its default.
        lines.append(f"  {name}: {_yaml_scalar(existing_value)}")
    return "\n".join(lines)


def _render_fields(fields: dict[str, FieldInfo], existing: dict) -> str:
    return "\n\n".join(
        _render_field(name, field, existing.get(name)) for name, field in fields.items()
    )


def _database_fields() -> dict[str, FieldInfo]:
    fields: dict[str, FieldInfo] = {}
    for model in DATABASE_MODELS:
        for name, field in model.model_fields.items():
            fields.setdefault(name, field)
    return fields


def generate_config(existing: dict | None = None) -> str:
    existing = existing or {}

    blocks = [HEADER]
    for section in SECTIONS:
        header = f"# {SECTION_DESCRIPTIONS[section]}\n"
        if section == "logging":
            blocks.append(header + LOGGING_SECTION)
        elif section == "database":
            blocks.append(
                header
                + "database:\n"
                + _render_fields(_database_fields(), existing.get("database") or {})
            )
        else:
            blocks.append(
                header
                + f"{section}:\n"
                + _render_fields(
                    SECTION_MODELS[section].model_fields, existing.get(section) or {}
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


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    output_path = Path(argv[0]) if argv else Path.cwd() / "config.yaml"

    existing_text = output_path.read_text() if output_path.exists() else None
    existing = yaml.safe_load(existing_text) if existing_text else None

    content = generate_config(existing)
    if content == existing_text:
        return

    if existing_text is not None:
        _backup(output_path, existing_text)
    output_path.write_text(content)


if __name__ == "__main__":
    main()
