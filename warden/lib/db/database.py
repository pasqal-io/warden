"""Warden db utils"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
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


def build_engine(cfg: DatabaseConfig) -> AsyncEngine:
    """Build the async engine for `cfg`.

    SQLite is put in WAL mode. With the default rollback journal, a connection
    holding an open read transaction makes any concurrent COMMIT fail straight
    away with SQLITE_BUSY ("database is locked"): SQLite does not consult the
    busy handler for that conflict, so `busy_timeout` is no help. The scheduler
    commits job updates while other tasks read the same file, so the conflict
    is reachable - and `job_update_commiter` would silently drop the update.
    WAL lets readers and a writer coexist. The pragma is stored in the database
    file, so it only has to be set once, but setting it per connection keeps it
    correct for a freshly created file.
    """
    engine = create_async_engine(build_db_url(cfg), echo=cfg.echo)

    if cfg.backend == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_wal(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
            finally:
                cursor.close()

    return engine
