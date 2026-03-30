"""Warden db utils"""

from sqlalchemy.engine.url import URL
from sqlalchemy.orm import declarative_base

from warden.lib.config import DatabaseConfig

Base = declarative_base()


def build_db_url(cfg: DatabaseConfig) -> str:
    if cfg.backend == "sqlite":
        return f"sqlite+aiosqlite:///{cfg.name}"

    if cfg.backend == "postgres":
        driver = "asyncpg"
        return URL.create(
            drivername=f"postgresql+{driver}",
            username=cfg.user,
            password=cfg.password,
            host=cfg.host,
            port=cfg.port,
            database=cfg.name,
        ).render_as_string(hide_password=False)

    if cfg.backend == "mariadb":
        driver = "asyncmy"
        return URL.create(
            drivername=f"mysql+{driver}",
            username=cfg.user,
            password=cfg.password,
            host=cfg.host,
            port=cfg.port,
            database=cfg.name,
        ).render_as_string(hide_password=False)

    raise ValueError(f"Unsupported backend: {cfg.backend}")
