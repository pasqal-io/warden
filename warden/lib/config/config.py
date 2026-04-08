"""Yaml config definition"""

from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import yaml
from pydantic import Field, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class SchedulerConfig(BaseSettings):
    strategy: Literal["FIFO"]

    db_polling_interval_s: float

    qpu_polling_interval_s: float
    qpu_polling_timeout_s: float

    job_polling_interval_s: float
    job_polling_timeout_s: float


class QPUConfig(BaseSettings):
    uri: str

    _client = PrivateAttr(default_factory=httpx.Client)

    @property
    def client(self):
        self._client.base_url = self.uri + API_PREFIX
        return self._client


class Config(BaseSettings):
    database: DatabaseConfig
    scheduler: SchedulerConfig
    logging: dict[str, Any]
    qpu: QPUConfig

    model_config = SettingsConfigDict(
        env_file=".env",
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
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        def _load_config_file(path: Path):
            if not path.exists():
                return {}

            with path.open() as f:
                data = yaml.safe_load(f) or {}

            return data

        def yaml_default_config():
            return _load_config_file(Path(__file__).parent / "config.sample.yaml")

        def yaml_config_source():
            return _load_config_file(Path(__file__).parent / "config.yaml")

        return (
            env_settings,  # Highest precedence: from env variables
            init_settings,  # from Config(...)
            dotenv_settings,  # from .env
            yaml_config_source,  # Lower precedence: from yaml
            yaml_default_config,  # Lowest precedence: default config file
        )
