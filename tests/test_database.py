"""Testing warden.lib.db.database"""

import pytest
from sqlalchemy import text

from warden.lib.config.config import SqliteConfig
from warden.lib.db.database import build_engine


@pytest.mark.asyncio
async def test_sqlite_commit_while_a_read_is_in_flight(tmp_path):
    """An unfinished read must not make a concurrent COMMIT fail.

    Cancelling a task while it sits inside a query - which the scheduler does
    on shutdown, and every scheduler test does on teardown - abandons its
    statement half-read, so that connection keeps SQLite's shared lock until it
    is closed. Under the default rollback journal the next COMMIT then fails
    right away with "database is locked"; SQLite does not consult the busy
    handler for that conflict, so `busy_timeout` is no help either. Only WAL
    lets the writer through.
    """
    engine = build_engine(SqliteConfig(name=str(tmp_path / "warden.db")))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE t (v INTEGER)"))
            await conn.execute(text("INSERT INTO t VALUES (1), (2), (3)"))

        # Stand-in for the connection of a task cancelled mid-query: a
        # statement left stepping, never finished, never rolled back.
        reader = await engine.connect()
        in_flight = await reader.stream(text("SELECT v FROM t"))
        await in_flight.fetchone()

        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO t VALUES (4)"))

        await reader.close()
    finally:
        await engine.dispose()
