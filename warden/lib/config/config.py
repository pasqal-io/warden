"""Yaml config definition"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import yaml
from pydantic import BeforeValidator, Field, PrivateAttr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

API_PREFIX = "/api/v1"


class SqliteConfig(BaseSettings):
    backend: Literal["sqlite"]
    name: str
    echo: bool = False


class PostgresConfig(BaseSettings):
    backend: Literal["postgres"]
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    name: str = Field(default="warden")
    user: str
    password: str
    echo: bool = False


class MariadbConfig(BaseSettings):
    backend: Literal["mariadb"]
    host: str = Field(default="localhost")
    port: int = Field(default=3306)
    name: str = Field(default="warden")
    user: str
    password: str
    echo: bool = False


DatabaseConfig = Annotated[
    SqliteConfig | PostgresConfig | MariadbConfig, Field(discriminator="backend")
]


class SchedulerStrategy(StrEnum):
    FIFO = "FIFO"


class SchedulerConfig(BaseSettings):
    strategy: SchedulerStrategy

    db_polling_interval_s: float

    qpu_polling_interval_s: float
    qpu_polling_timeout_s: float

    job_polling_interval_s: float
    job_polling_timeout_s: float


class QPUConfig(BaseSettings):
    uri: str

    retry_max: int
    retry_sleep_s: float

    _client: httpx.Client = PrivateAttr(default_factory=httpx.Client)

    @property
    def client(self):
        self._client.base_url = self.uri + API_PREFIX
        return self._client


def coerce_to_str(v):
    for item in v:
        if type(item) not in (str, int):
            raise ValueError("User uid must be a string or an integer")
    return [str(item) for item in v]


class APIConfig(BaseSettings):
    host: str
    port: int
    # processing authorized_users as strings but allowing users to input numbers
    authorized_users: Annotated[list[str], BeforeValidator(coerce_to_str)]


class Config(BaseSettings):
    api: APIConfig = Field(
        default_factory=lambda: APIConfig(
            host="0.0.0.0",
            port=8006,
            authorized_users=[],
        )
    )
    database: DatabaseConfig = Field(
        default_factory=lambda: SqliteConfig(backend="sqlite", name="warden.db")
    )
    scheduler: SchedulerConfig = Field(
        default_factory=lambda: SchedulerConfig(
            strategy=SchedulerStrategy.FIFO,
            db_polling_interval_s=1,
            qpu_polling_interval_s=5,
            qpu_polling_timeout_s=-1,
            job_polling_interval_s=5,
            job_polling_timeout_s=-1,
        )
    )
    logging: dict[str, Any] = Field(default_factory=dict)
    qpu: QPUConfig = Field(
        default_factory=lambda: QPUConfig(
            uri="http://localhost:8000",
            retry_max=10,
            retry_sleep_s=1,
        )
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WARDEN_",
        env_nested_delimiter="_",
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
