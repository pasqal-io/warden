"""Shared DB backend selection and configs for parametrized API/scheduler tests."""

import os

import pytest

from warden.lib.config.config import MariadbConfig, PostgresConfig, SqliteConfig

TEST_DATABASE_BACKENDS: tuple[str, ...] = ("sqlite", "postgres", "mariadb")


def config_backend_params() -> list[str]:
    """Backends for parametrized DB fixtures.

    If ``WARDEN_TEST_DATABASE_BACKEND``
    is unset, all backends are used. Otherwise use a comma-separated subset of
    ``sqlite``, ``postgres``, ``mariadb``.
    """
    raw = os.environ.get("WARDEN_TEST_DATABASE_BACKEND", "").strip()
    if not raw:
        return list(TEST_DATABASE_BACKENDS)
    chosen = [b.strip() for b in raw.split(",") if b.strip()]
    if not chosen:
        return list(TEST_DATABASE_BACKENDS)
    invalid = [b for b in chosen if b not in TEST_DATABASE_BACKENDS]
    if invalid:
        msg = (
            f"WARDEN_TEST_DATABASE_BACKEND: "
            f"unknown backend(s) {invalid!r}; "
            f"expected comma-separated values from {list(TEST_DATABASE_BACKENDS)}"
        )
        raise pytest.UsageError(msg)
    return chosen


def _in_container() -> bool:
    return os.path.isfile("/.dockerenv")


def _default_pg_host() -> str:
    if "PG_TEST_HOST" in os.environ:
        return os.environ["PG_TEST_HOST"]
    return "warden-db-postgres" if _in_container() else "localhost"


def _default_mariadb_host() -> str:
    if "MARIADB_TEST_HOST" in os.environ:
        return os.environ["MARIADB_TEST_HOST"]
    return "warden-db-mariadb" if _in_container() else "127.0.0.1"


def _pg_database_name() -> str:
    return os.environ.get("PG_TEST_DB", "").strip() or "warden"


def _mariadb_database_name() -> str:
    return os.environ.get("MARIADB_TEST_DB", "").strip() or "warden"


def build_database_config(
    backend: str,
) -> SqliteConfig | PostgresConfig | MariadbConfig:
    """Build a database config for ``backend`` (sqlite path required for sqlite)."""
    if backend == "sqlite":
        return SqliteConfig(
            name="/tmp/warden_test.db",
            backend="sqlite",
            echo=False,
        )
    if backend == "postgres":
        pytest.importorskip("asyncpg")
        return PostgresConfig(
            backend="postgres",
            host=_default_pg_host(),
            port=int(os.environ.get("PG_TEST_PORT", "5432")),
            name=_pg_database_name(),
            user=os.environ.get("PG_TEST_USER", "wardenuser"),
            password=os.environ.get("PG_TEST_PASSWORD", "secret"),
            echo=False,
        )
    if backend == "mariadb":
        pytest.importorskip("asyncmy")
        return MariadbConfig(
            backend="mariadb",
            host=_default_mariadb_host(),
            port=int(os.environ.get("MARIADB_TEST_PORT", "3306")),
            name=_mariadb_database_name(),
            user=os.environ.get("MARIADB_TEST_USER", "root"),
            password=os.environ.get("MARIADB_TEST_PASSWORD", "secret"),
            echo=False,
        )
    raise ValueError(f"Unsupported backend: {backend!r}")
