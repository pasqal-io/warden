"""Yaml config definition"""

import json
import ssl
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
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


class SqliteConfig(WardenSettings):
    backend: Literal["sqlite"] = "sqlite"
    name: str = "warden.db"
    echo: bool = False


class PostgresConfig(WardenSettings):
    backend: Literal["postgres"] = "postgres"
    host: str = "localhost"
    port: int = 5432
    name: str = "warden"
    user: str
    password: str
    echo: bool = False


class MariadbConfig(WardenSettings):
    backend: Literal["mariadb"] = "mariadb"
    host: str = "localhost"
    port: int = 3306
    name: str = "warden"
    user: str
    password: str
    echo: bool = False


DatabaseConfig = Annotated[
    SqliteConfig | PostgresConfig | MariadbConfig, Field(discriminator="backend")
]


class SchedulerStrategy(StrEnum):
    FIFO = "FIFO"


class SchedulerConfig(WardenSettings):
    strategy: SchedulerStrategy = SchedulerStrategy.FIFO

    db_polling_interval_s: float = 1

    qpu_polling_interval_s: float = 5
    qpu_polling_timeout_s: float = -1

    job_polling_interval_s: float = 5
    job_polling_timeout_s: float = -1


class QPUConfig(WardenSettings):
    uri: str = "http://localhost:8000"

    retry_max: int = 10
    retry_sleep_s: float = 1

    # TLS verification policy for requests to the QPU backend. Mirrors httpx's
    # ``verify`` argument, with an extra "system" mode:
    #   "system"        -> verify against the OS trust store, e.g.
    #                      /etc/pki/ca-trust, /etc/ssl/certs (default)
    #   true            -> verify against certifi's CA bundle (httpx default)
    #   false           -> disable verification (INSECURE; dev/e2e only)
    #   "<path/to.pem>" -> verify against a specific CA bundle / cert file
    tls_verify: bool | str = "system"

    _client: httpx.Client | None = PrivateAttr(default=None)

    @property
    def verify(self) -> bool | str | ssl.SSLContext:
        """Translate ``tls_verify`` into an httpx ``verify`` argument."""
        if self.tls_verify == "system":
            # ssl.create_default_context() loads OpenSSL's default verify paths,
            # which is where update-ca-trust publishes OS trust anchors.
            return ssl.create_default_context()
        return self.tls_verify

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(verify=self.verify)
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
    host: str = "0.0.0.0"
    port: int = Field(default=8006, ge=1, le=65535)

    # processing authorized_users as strings but allowing users to input numbers
    authorized_users: Annotated[list[str], BeforeValidator(coerce_to_str)] = []
    admin_users: Annotated[
        list[str], BeforeValidator(coerce_to_str), AfterValidator(ensure_non_empty)
    ] = ["0"]


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

            return data

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
            YamlSettingsSource(
                settings_cls, Path(__file__).parent / "config.sample.yaml"
            ),
        )
