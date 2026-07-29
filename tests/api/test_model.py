"""Testing Job/Session model hybrid properties: instance-level vs SQL expression."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from warden.lib.models import Job, Session

NOW = datetime(2026, 1, 1, 12, 0, 0)


@pytest.mark.asyncio
async def test_job_hybrid_properties_match(db_session_factory):
    """Assert effective_end/execution_time/wait_time agree whether read on a
    DB-loaded instance or computed in DB by the SQL expression, and that the
    expression returns an int (not a float/Decimal).

    Uses whole-second offsets: MariaDB DATETIME columns have no sub-second
    precision (fsp=0), so fractional inputs would not round-trip identically
    across backends and the instance/expression comparison would become
    backend-sensitive.
    """
    session = Session(
        created_at=NOW,
        revoked_at=NOW + timedelta(hours=2),
        user_id="1000",
        slurm_job_id="0",
    )
    job = Job(
        status="CANCELED",
        logs="",
        shots=100,
        sequence="",
        created_at=NOW,
        scheduled_at=NOW,
        started_at=NOW + timedelta(minutes=5),
        ended_at=None,
        canceled_at=NOW + timedelta(minutes=35),
        session=session,
    )

    async with db_session_factory() as db_session:
        db_session.add_all([session, job])
        await db_session.commit()
        job_id = job.id

    # Fresh session so `loaded_job` is actually read back from the DB,
    # not the in-memory object we just built.
    async with db_session_factory() as db_session:
        loaded_job = await db_session.get(Job, job_id)

        expr_stmt = select(
            Job.effective_end,
            Job.execution_time,
            Job.wait_time,
        ).where(Job.id == job_id)
        row = (await db_session.execute(expr_stmt)).one()

    assert loaded_job.effective_end == row.effective_end
    assert loaded_job.execution_time == row.execution_time
    assert loaded_job.wait_time == row.wait_time

    # The SQL expression must return a real int, not a float/Decimal (which
    # would still satisfy the numeric comparisons below).
    assert isinstance(row.execution_time, int)
    assert isinstance(row.wait_time, int)

    # Pin the actual values (whole-second spans).
    assert row.execution_time == 30 * 60
    assert row.wait_time == 5 * 60


@pytest.mark.asyncio
async def test_session_hybrid_properties_match(db_session_factory):
    """Assert Session.duration agrees whether read on a loaded instance or
    computed in DB by the SQL expression, and returns an int. Whole-second
    offset keeps it backend-agnostic (see the job test)."""
    session = Session(
        created_at=NOW,
        revoked_at=NOW + timedelta(minutes=45),
        user_id="1000",
        slurm_job_id="0",
    )

    async with db_session_factory() as db_session:
        db_session.add(session)
        await db_session.commit()
        session_id = session.id

    # Fresh session so `loaded_session` is actually read back from the DB,
    # not the in-memory object we just built.
    async with db_session_factory() as db_session:
        loaded_session = await db_session.get(Session, session_id)

        expr_stmt = select(Session.duration).where(Session.id == session_id)
        row = (await db_session.execute(expr_stmt)).one()

    assert loaded_session.duration == row.duration
    assert isinstance(row.duration, int)
    assert row.duration == 45 * 60
