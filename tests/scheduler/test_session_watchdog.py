"""Testing warden.scheduler.session_watchdog"""

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from warden.lib.config import Config, SchedulerConfig
from warden.lib.models import Job, Session
from warden.scheduler.session_watchdog import session_watchdog

OLD = datetime.now(timezone.utc) - timedelta(hours=1)


def build_watchdog_conf(session_idle_timeout_s: float) -> Config:
    return Config(
        scheduler=SchedulerConfig(
            db_polling_interval_s=0.01,
            session_idle_timeout_s=session_idle_timeout_s,
        ),
    )


async def run_briefly(conf: Config, db_session_maker: async_sessionmaker) -> None:
    """Run the watchdog for a few polling intervals, then stop it."""
    task = asyncio.create_task(session_watchdog(conf, db_session_maker))
    try:
        await asyncio.sleep(0.2)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_session_watchdog_revokes_idle_session_and_cancels_its_jobs(
    db_session_maker: async_sessionmaker,
):
    """A session with no recent job activity gets revoked, and its pending job canceled."""
    session_record = Session(user_id="1234", slurm_job_id="1", created_at=OLD)
    stale_job = Job(
        sequence="{}",
        shots=100,
        status="PENDING",
        session=session_record,
        created_at=OLD,
    )

    async with db_session_maker() as session:
        session.add_all([session_record, stale_job])
        await session.commit()

    conf = build_watchdog_conf(session_idle_timeout_s=0.05)
    await run_briefly(conf, db_session_maker)

    async with db_session_maker() as session:
        refreshed_session = await session.get(Session, session_record.id)
        refreshed_job = await session.get(Job, stale_job.id)
        assert refreshed_session.revoked_at is not None
        assert refreshed_job.canceled_at is not None
        assert refreshed_job.status == "CANCELED"


@pytest.mark.asyncio
async def test_session_watchdog_does_not_revoke_session_with_recent_job(
    db_session_maker: async_sessionmaker,
):
    """A session whose most recent job is within the idle window stays untouched."""
    session_record = Session(user_id="1234", slurm_job_id="1", created_at=OLD)
    recent_job = Job(
        sequence="{}",
        shots=100,
        status="PENDING",
        session=session_record,
    )

    async with db_session_maker() as session:
        session.add_all([session_record, recent_job])
        await session.commit()

    conf = build_watchdog_conf(session_idle_timeout_s=3600)
    await run_briefly(conf, db_session_maker)

    async with db_session_maker() as session:
        refreshed_session = await session.get(Session, session_record.id)
        assert refreshed_session.revoked_at is None


@pytest.mark.asyncio
async def test_session_watchdog_disabled_when_timeout_negative(
    db_session_maker: async_sessionmaker,
):
    """session_idle_timeout_s = -1 disables the watchdog entirely."""
    session_record = Session(user_id="1234", slurm_job_id="1", created_at=OLD)

    async with db_session_maker() as session:
        session.add(session_record)
        await session.commit()

    conf = build_watchdog_conf(session_idle_timeout_s=-1)
    await run_briefly(conf, db_session_maker)

    async with db_session_maker() as session:
        refreshed_session = await session.get(Session, session_record.id)
        assert refreshed_session.revoked_at is None
