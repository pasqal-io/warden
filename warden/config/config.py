from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Literal
import yaml
from pathlib import Path


class DatabaseConfig(BaseSettings):
    backend: Literal["sqlite", "postgres", "mariadb"]

    host: str | None = None
    port: int | None = None
    name: str | None = "warden.db"
    user: str | None = None
    password: str | None = None

    echo: bool = False


class Config(BaseSettings):
    database: DatabaseConfig
    logging: dict[str, Any]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="_",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        def yaml_config_source():
            path = Path("warden/config/config.yaml")
            if not path.exists():
                return {}

            with path.open() as f:
                data = yaml.safe_load(f) or {}

            return data

        return (
            init_settings,
            yaml_config_source,  # from yaml
            dotenv_settings,  # from dotenv
            env_settings,  # from env variables
            file_secret_settings,
        )
