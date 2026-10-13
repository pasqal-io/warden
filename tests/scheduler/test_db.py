"""Tests for the scheduler DB commit worker"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from warden.lib.models import Job, Session
from warden.scheduler.db import job_update_commiter
from warden.scheduler.types import JobUpdate


async def _job_status(db_session_maker, job_id: int) -> str:
    async with db_session_maker() as session:
        return (
            await session.execute(select(Job.status).where(Job.id == job_id))
        ).scalar_one()


@pytest.mark.asyncio
async def test_terminal_update_does_not_wait_for_locked_session(
    db_session_maker, config_db
):
    """A finished job is stored while session revocation holds the session row.

    Revocation locks the session and then its jobs. The commit worker must not
    hold the job row while waiting for the session, or the two deadlock.
    """
    if config_db.database.backend == "sqlite":
        pytest.skip("SQLite serializes all writers; no row-level lock ordering")

    stale = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with db_session_maker() as session:
        record = Session(user_id="1000", scheduler_job_id="1", idle_expires_at=stale)
        job = Job(session=record, shots=1, sequence="{}", status="RUNNING")
        session.add(job)
        await session.commit()
        job_id, session_id = job.id, record.id

    queue: asyncio.Queue[JobUpdate] = asyncio.Queue()
    commiter = asyncio.create_task(
        job_update_commiter(
            job_id, queue, db_session_maker, session_idle_timeout_s=3600
        )
    )
    try:
        async with db_session_maker() as revoker:
            async with revoker.begin():
                await revoker.execute(
                    select(Session).where(Session.id == session_id).with_for_update()
                )
                await queue.put(JobUpdate(status="DONE", new_logs="", result="{}"))
                for _ in range(50):
                    if await _job_status(db_session_maker, job_id) == "DONE":
                        break
                    await asyncio.sleep(0.1)
                assert await _job_status(db_session_maker, job_id) == "DONE"
                # Revocation continues with the session's jobs.
                await revoker.execute(
                    update(Job)
                    .where(Job.session_id == session_id)
                    .values(canceled_at=datetime.now(timezone.utc))
                )
        await asyncio.wait_for(queue.join(), timeout=10)
    finally:
        commiter.cancel()

    async with db_session_maker() as session:
        refreshed = (
            await session.execute(select(Session).where(Session.id == session_id))
        ).scalar_one()
    idle_expires_at = refreshed.idle_expires_at
    if idle_expires_at.tzinfo is None:
        idle_expires_at = idle_expires_at.replace(tzinfo=timezone.utc)
    assert idle_expires_at > datetime.now(timezone.utc)
