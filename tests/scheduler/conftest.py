"""Pytest fixture and configurations"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from warden.lib.db.database import Base, build_engine


@pytest_asyncio.fixture(scope="function")
async def db_engine(config_db):
    engine = build_engine(config_db.database)

    async with engine.begin() as conn:
        # Create all tables once
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine

        async with engine.begin() as conn:
            # Delete tables
            await conn.run_sync(Base.metadata.drop_all)
    finally:
        # Always dispose: every backend shares one database across the test
        # session, so an engine left open on a failing teardown leaks its
        # connections - and their transactions - into every later test.
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session_maker(db_engine):
    """Deleting tables after tests so that we don't have to worry about unique ID"""
    yield async_sessionmaker(db_engine, expire_on_commit=False)

    async with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
