from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated, Any, Literal
import yaml
from pathlib import Path



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

DatabaseConfig = Annotated[SqliteConfig | PostgresConfig | MariadbConfig, Field(discriminator="backend")]

class QPUConfig(BaseSettings):
    url: str


class Config(BaseSettings):
    database: DatabaseConfig
    logging: dict[str, Any]
    qpu: QPUConfig

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
        def _load_config_file(path: Path):
            if not path.exists():
                return {}

            with path.open() as f:
                data = yaml.safe_load(f) or {}

            return data

        def yaml_default_config():
            return _load_config_file(Path("warden/config/config.sample.yaml"))

        def yaml_config_source():
            return _load_config_file(Path("warden/config/config.yaml"))

        return (
            env_settings,         # Highest precedence: from env variables
            init_settings,        # from Config(...)
            dotenv_settings,      # from .env
            yaml_config_source,   # Lower precedence: from yaml
            yaml_default_config,  # Lowest precedence: default config file
        )
