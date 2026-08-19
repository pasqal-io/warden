"""Generate config.yaml from config.py's field defaults and descriptions."""

import re
import textwrap
from enum import Enum
from pathlib import Path

import yaml
from pydantic import AliasChoices, BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from warden.lib.config.config import (
    CONFIG_FILENAME,
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
# shows the built-in default. Uncomment only the keys you want to override.
# (except the logging section which has no in-code default and is always active)"""

# `logging:` has no in-code default (it's free-form dictConfig), so this is
# only the fallback used when there's no previous config.yaml to keep it from
# (see _existing_logging_section).
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
LOGGING_HEADER_RE = re.compile(r"^logging:\s*$", re.MULTILINE)
COMMENT_WIDTH = 88
INDENT_UNIT = "  "


def _yaml_scalar(value) -> str:
    if isinstance(value, Enum):
        value = value.value
    # First line only: safe_dump appends a "...\n" document-end marker after
    # bare scalars (but not after flow-style collections).
    return yaml.safe_dump(value, default_flow_style=True).splitlines()[0]


def _wrap_comment(text: str, indent: str) -> list[str]:
    prefix = f"{indent}# "
    return textwrap.wrap(
        text, width=COMMENT_WIDTH, initial_indent=prefix, subsequent_indent=prefix
    )


def _nested_model(field: FieldInfo) -> type[BaseModel] | None:
    annotation = field.annotation
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _lookup_keys(name: str, field: FieldInfo) -> list[str]:
    # Every field gets a kebab-case validation_alias (see to_kebab in
    # config.py). A renamed field could also declare AliasChoices(new, old)
    # to keep reading a previous name -- either way, a value already set
    # under any of those keys should still be picked up here.
    keys = [name]
    alias = field.validation_alias
    if isinstance(alias, str):
        candidates = [alias]
    elif isinstance(alias, AliasChoices):
        candidates = [c for c in alias.choices if isinstance(c, str)]
    else:
        candidates = []  # AliasPath (nested lookup) doesn't apply here.
    keys.extend(key for key in candidates if key not in keys)
    return keys


def _existing_value(existing: dict, name: str, field: FieldInfo):
    for key in _lookup_keys(name, field):
        value = existing.get(key)
        if value is not None:
            return value
    return None


def _render_field(name: str, field: FieldInfo, existing_value, depth: int) -> str:
    indent = INDENT_UNIT * depth
    lines = [
        wrapped
        for paragraph in (field.description or "").split("\n")
        if paragraph
        for sentence in SENTENCE_RE.split(paragraph)
        if sentence
        for wrapped in _wrap_comment(sentence, indent)
    ]

    nested_model = _nested_model(field)
    if nested_model is not None:
        nested_existing = existing_value if isinstance(existing_value, dict) else {}
        lines.append(f"{indent}{name}:")
        lines.append(
            _render_fields(nested_model.model_fields, nested_existing, depth + 1)
        )
        return "\n".join(lines)

    if field.default is PydanticUndefined:
        lines.append(f"{indent}# {name}: ...  # required, no default")
    else:
        lines.append(f"{indent}# {name}: {_yaml_scalar(field.default)}")
    if existing_value is not None:
        # Keep the value the user already set, uncommented, below its default.
        lines.append(f"{indent}{name}: {_yaml_scalar(existing_value)}")
    return "\n".join(lines)


def _render_fields(fields: dict[str, FieldInfo], existing: dict, depth: int) -> str:
    return "\n\n".join(
        _render_field(name, field, _existing_value(existing, name, field), depth)
        for name, field in fields.items()
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
    existing: dict | None = None, existing_text: str | None = None
) -> str:
    """Generate a new config from model definition and eventual previous fields set"""
    existing = existing or {}

    blocks = [HEADER]
    for section in SECTIONS:
        header = f"# {SECTION_DESCRIPTIONS[section]}\n"
        if section == "logging":
            blocks.append(
                header + (_existing_logging_section(existing_text) or LOGGING_SECTION)
            )
        elif section == "database":
            blocks.append(
                header
                + "database:\n"
                + _render_fields(_database_fields(), existing.get("database") or {}, 1)
            )
        else:
            blocks.append(
                header
                + f"{section}:\n"
                + _render_fields(
                    SECTION_MODELS[section].model_fields,
                    existing.get(section) or {},
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


def main() -> None:
    """Call the script to generate a new config.yaml file"""
    output_path = Path.cwd() / CONFIG_FILENAME

    existing_text = output_path.read_text() if output_path.exists() else None
    existing = None
    if existing_text:
        try:
            Config()
            loaded = yaml.safe_load(existing_text)
            existing = loaded
        except (yaml.YAMLError, ValidationError):
            print("Previous config.yaml is not valid YAML/Config: ignore it.")

    content = generate_config(existing, existing_text)
    if content == existing_text:
        return

    if existing_text is not None:
        _backup(output_path, existing_text)
    output_path.write_text(content)


if __name__ == "__main__":
    main()
