"""Yaml config definition"""

import json
import ssl
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx2
import yaml
from pydantic import (
    AfterValidator,
    AliasGenerator,
    BeforeValidator,
    Field,
    PrivateAttr,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

API_PREFIX = "/api/v1"


def to_kebab(snake: str) -> str:
    return snake.replace("_", "-")


class WardenSettings(BaseSettings):
    # Give kebab-case aliases to all fields but still allow validating by field name
    model_config = SettingsConfigDict(
        validate_by_name=True,
        alias_generator=AliasGenerator(validation_alias=to_kebab),
    )


DATABASE_BACKEND_DESCRIPTION = (
    "Database backend. Warden supports sqlite, postgres or mariadb."
)
DATABASE_HOST_DESCRIPTION = (
    "Address to connect to the database. Only used for PostgreSQL and MariaDB."
)
DATABASE_USER_DESCRIPTION = (
    "Database user used to connect to the database. "
    "Mandatory for PostgreSQL and MariaDB."
)
DATABASE_PASSWORD_DESCRIPTION = (
    "Database password used to connect to the database. Mandatory for PostgreSQL "
    "and MariaDB. Should be set via the WARDEN_DATABASE_PASSWORD environment "
    "variable rather than in the config file."
)
DATABASE_ECHO_DESCRIPTION = "Optional, SQLAlchemy echo (log all SQL statements)."


class SqliteConfig(WardenSettings):
    backend: Literal["sqlite"] = Field(
        default="sqlite", description=DATABASE_BACKEND_DESCRIPTION
    )
    name: str = Field(
        default="warden.db",
        description="For SQLite, the database name is the filename of the database file.",
    )
    echo: bool = Field(default=False, description=DATABASE_ECHO_DESCRIPTION)


class PostgresConfig(WardenSettings):
    backend: Literal["postgres"] = Field(
        default="postgres", description=DATABASE_BACKEND_DESCRIPTION
    )
    host: str = Field(default="localhost", description=DATABASE_HOST_DESCRIPTION)
    port: int = Field(
        default=5432,
        description="Port to connect to the database. Default for PostgreSQL, 3306 for MariaDB.",
    )
    name: str = Field(
        default="warden",
        description="For PostgreSQL and MariaDB, the database name is the name of the database.",
    )
    user: str = Field(description=DATABASE_USER_DESCRIPTION)
    password: str = Field(description=DATABASE_PASSWORD_DESCRIPTION)
    echo: bool = Field(default=False, description=DATABASE_ECHO_DESCRIPTION)


class MariadbConfig(WardenSettings):
    backend: Literal["mariadb"] = Field(
        default="mariadb", description=DATABASE_BACKEND_DESCRIPTION
    )
    host: str = Field(default="localhost", description=DATABASE_HOST_DESCRIPTION)
    port: int = Field(
        default=3306,
        description="Port to connect to the database. Default for MariaDB, 5432 for PostgreSQL.",
    )
    name: str = Field(
        default="warden",
        description="For PostgreSQL and MariaDB, the database name is the name of the database.",
    )
    user: str = Field(description=DATABASE_USER_DESCRIPTION)
    password: str = Field(description=DATABASE_PASSWORD_DESCRIPTION)
    echo: bool = Field(default=False, description=DATABASE_ECHO_DESCRIPTION)


DatabaseConfig = Annotated[
    SqliteConfig | PostgresConfig | MariadbConfig, Field(discriminator="backend")
]


class SchedulerStrategy(StrEnum):
    FIFO = "FIFO"


class SchedulerConfig(WardenSettings):
    strategy: SchedulerStrategy = Field(
        default=SchedulerStrategy.FIFO,
        description=(
            "Job scheduling strategy. Available strategies: "
            "FIFO (priority to the oldest job pending in the database)."
        ),
    )

    db_polling_interval_s: float = Field(
        default=1,
        description=(
            "Time interval in seconds between checks on the database "
            "for a new job to schedule."
        ),
    )

    qpu_polling_interval_s: float = Field(
        default=5,
        description="Time interval in seconds between checks of the QPU status.",
    )
    qpu_polling_timeout_s: float = Field(
        default=-1,
        description=(
            "Maximum time in seconds the scheduler will wait for the QPU to be "
            "operational at the start of a job. If the QPU is not operational "
            'after this time, the scheduled job will return with status "ERROR". '
            "Set to -1 for no time limit."
        ),
    )

    job_polling_interval_s: float = Field(
        default=5,
        description=(
            "Time interval in seconds between checks of the status of the "
            "job running on the QPU."
        ),
    )
    job_polling_timeout_s: float = Field(
        default=-1,
        description=(
            "Maximum time in seconds the scheduler will wait for the job to "
            "finish execution on the QPU. If the job is not done after this "
            "time, the scheduler will cancel the job on the QPU and return "
            'with status "CANCELED". Set to -1 for no time limit.'
        ),
    )


class QPUConfig(WardenSettings):
    uri: str = Field(
        default="http://localhost:8000", description="Local Pasqal QPU API URI."
    )

    retry_max: int = Field(
        default=10,
        description=(
            "Max number of retries to the QPU API in case of transient errors "
            "during requests."
        ),
    )
    retry_sleep_s: float = Field(
        default=1, description="Time in seconds between request retries."
    )

    tls_verify: bool | str = Field(
        default=True,
        description=(
            "TLS verification policy for requests to the QPU backend. Only "
            "relevant when 'uri' uses https. Mirrors httpx2's `verify` argument: "
            "true -> verify against the OS trust store (httpx2 default); "
            "false -> disable verification (INSECURE; dev/e2e only); "
            '"<path/to.pem>" -> verify against a specific CA bundle / certificate file.'
        ),
    )

    _client: httpx2.Client | None = PrivateAttr(default=None)

    @property
    def verify(self) -> bool | ssl.SSLContext:
        """Translate ``tls_verify`` into an httpx ``verify`` argument."""
        if isinstance(self.tls_verify, str):
            return ssl.create_default_context(cafile=self.tls_verify)
        return self.tls_verify

    @property
    def client(self) -> httpx2.Client:
        if self._client is None:
            self._client = httpx2.Client(verify=self.verify)
        self._client.base_url = self.uri + API_PREFIX
        return self._client


def coerce_to_str(v):
    if isinstance(v, str):
        # env vars for nested list fields (e.g. WARDEN_API_AUTHORIZED-USERS)
        # arrive as a raw JSON string instead of a parsed list, since
        # pydantic-settings' nested-key resolver doesn't recognize aliased
        # leaf fields as complex when env_prefix_target="all" is set.
        try:
            v = json.loads(v)
        except ValueError:
            pass
    if not isinstance(v, list):
        raise ValueError("User uids must be provided as a list")
    for item in v:
        if type(item) not in (str, int):
            raise ValueError("User uid must be a string or an integer")
    return [str(item) for item in v]


def ensure_non_empty(v: list[str]) -> list[str]:
    # admin_users must list at least one uid (e.g. the user running the
    # spank plugin), otherwise Warden cannot create sessions on behalf of users.
    if not v:
        raise ValueError("admin_users must not be empty")
    return v


class APIConfig(WardenSettings):
    host: str = Field(default="0.0.0.0", description="API bind address.")
    port: int = Field(default=8006, ge=1, le=65535, description="API bind port.")

    # processing authorized_users as strings but allowing users to input numbers
    authorized_users: Annotated[list[str], BeforeValidator(coerce_to_str)] = Field(
        default=[],
        description=(
            "List of user ids authorized to create new jobs on the QPU by "
            "creating a new session. All entries must be strings or integers. "
            "If empty/unset, all users are authorized."
        ),
    )
    admin_users: Annotated[
        list[str], BeforeValidator(coerce_to_str), AfterValidator(ensure_non_empty)
    ] = Field(
        default=["0"],
        description=(
            "List of admin uids authorized to set the availability of the QPU "
            "and create sessions on behalf of users. All entries must be strings "
            "or integers. Must not be empty, and must include the uid running "
            "the spank plugin."
        ),
    )


class Config(WardenSettings):
    api: APIConfig = APIConfig()
    database: DatabaseConfig = SqliteConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    logging: dict[str, Any] = {}
    qpu: QPUConfig = QPUConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WARDEN_",
        env_nested_delimiter="_",
        env_prefix_target="all",
    )

    @model_validator(mode="after")
    def _ensure_log_directories(self):
        handlers = self.logging.get("handlers")
        if not isinstance(handlers, dict):
            return self

        for handler_conf in handlers.values():
            if not isinstance(handler_conf, dict):
                continue

            filename = handler_conf.get("filename")
            if not filename:
                continue

            path = Path(str(filename))
            parent = path.parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)

        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        def _load_config_file(path: Path):
            if not path.exists():
                return {}

            with path.open() as f:
                data = yaml.safe_load(f) or {}

            # Parse empty YAML section as empty dict instead of Null
            return {k: v for k, v in data.items() if v is not None}

        class YamlSettingsSource(PydanticBaseSettingsSource):
            def __init__(self, settings_cls: type[BaseSettings], path: Path):
                super().__init__(settings_cls)
                self.path = path

            def get_field_value(self, field, field_name: str):
                return None, field_name, False

            def __call__(self) -> dict[str, Any]:
                return _load_config_file(self.path)

        return (
            env_settings,  # Highest precedence: from env variables
            init_settings,  # from Config(...)
            dotenv_settings,  # from .env
            YamlSettingsSource(settings_cls, Path.cwd() / "config.yaml"),
        )
