"""Testing Job/Session model hybrid properties: instance-level vs SQL expression."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from warden.lib.models import Job, Session

NOW = datetime(2026, 1, 1, 12, 0, 0)


@pytest.mark.asyncio
async def test_job_hybrid_properties_match_instance_and_expression(
    app, serialized_sequence
):
    """Assert effective_end/execution_time/wait_time agree whether read on a
    DB-loaded instance (Python getter) or computed by the SQL expression.

    Uses whole-minute offsets so the comparison isn't sensitive to the
    sub-second rounding differences duration_seconds has across backends.
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
        sequence=serialized_sequence,
        created_at=NOW,
        scheduled_at=NOW,
        started_at=NOW + timedelta(minutes=5),
        ended_at=None,
        canceled_at=NOW + timedelta(minutes=35),
        session=session,
    )

    session_factory = app.state.db_session_factory
    async with session_factory() as db_session:
        db_session.add_all([session, job])
        await db_session.commit()
        job_id = job.id

    # Fresh session so `loaded_job` is actually read back from the DB,
    # not the in-memory object we just built.
    async with session_factory() as db_session:
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

    # Pin the actual values, not just instance/expression agreement.
    assert row.execution_time == 30 * 60
    assert row.wait_time == 5 * 60


@pytest.mark.asyncio
async def test_session_duration_matches_instance_and_expression(app):
    """Assert Session.duration agrees whether read on a DB-loaded instance
    (Python getter) or computed by the SQL expression."""
    session = Session(
        created_at=NOW,
        revoked_at=NOW + timedelta(minutes=45),
        user_id="1000",
        slurm_job_id="0",
    )

    session_factory = app.state.db_session_factory
    async with session_factory() as db_session:
        db_session.add(session)
        await db_session.commit()
        session_id = session.id

    # Fresh session so `loaded_session` is actually read back from the DB,
    # not the in-memory object we just built.
    async with session_factory() as db_session:
        loaded_session = await db_session.get(Session, session_id)

        expr_stmt = select(Session.duration).where(Session.id == session_id)
        row = (await db_session.execute(expr_stmt)).one()

    assert loaded_session.duration == row.duration
    assert row.duration == 45 * 60
