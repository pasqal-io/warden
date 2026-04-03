"""Pytest fixture and configurations"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from warden.lib.config.config import Config, SqliteConfig
from warden.lib.db.database import Base, build_db_url
from warden.lib.models import Job, Session


class Helpers:
    @staticmethod
    async def create_n_jobs(db_session_maker: async_sessionmaker, n_jobs: int):
        """Creates n_jobs mock jobs to run in the warden db"""
        SLURM_USER_ID = "1234"

        jobs_to_run = [
            Job(
                id=i,
                sequence="{}",
                status="PENDING",
                shots=100,
                session=Session(slurm_job_id=1, user_id=SLURM_USER_ID),
            )
            for i in range(n_jobs)
        ]

        async with db_session_maker() as session:
            session.add_all(jobs_to_run)
            await session.commit()


@pytest.fixture
def helpers():
    yield Helpers


@pytest.fixture(scope="session")
def config_db():
    db_config = SqliteConfig(backend="sqlite", name="scheduler_test.db", echo=False)
    yield Config(database=db_config)


@pytest_asyncio.fixture(scope="session")
async def db_engine(config_db):
    engine = create_async_engine(build_db_url(config_db.database))

    async with engine.begin() as conn:
        # Create all tables once
        await conn.run_sync(Base.metadata.create_all)
    yield engine

    async with engine.begin() as conn:
        # Delete tables
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session_maker(db_engine):
    """Deleting tables after tests so that we don't have to worry about unique ID"""
    yield async_sessionmaker(db_engine, expire_on_commit=False)

    async with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
