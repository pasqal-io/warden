"""
Testing possible race conditions between the api cancelling a job and the scheduler
"""

import asyncio
from typing import cast

import pytest
from sqlalchemy import Update, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import mock_munge_auth
from warden.lib.config import SchedulerStrategy
from warden.lib.models.jobs import Job
from warden.lib.models.sessions import Session
from warden.scheduler.strategy import schedulers

##########################################################################
####################### Repeated behavior testing ########################
##########################################################################


@pytest.mark.asyncio
async def test_repeated_job_cancel_and_scheduler_pick_race(
    client, app, serialized_sequence: str
):
    """Assert racing a real cancel against a real scheduler pick never lets
    a job end up CANCELED and scheduled at once

    1. Create a PENDING job for a given user
    2. Run the API cancel and the scheduler's `get_next_job` concurrently on
       that job, with no control over which one the event loop runs first
    3. Assert the job never ends up with status CANCELED and a
       `scheduled_at` set. Whoever claims the jobs first wins.
    4. Repeat over fresh jobs, since which side wins isn't controlled here
    """
    user_id = 1000
    async_session = app.state.db_session_factory
    scheduler = schedulers[SchedulerStrategy.FIFO]

    for _ in range(40):
        job = Job(
            session=Session(user_id=str(user_id), slurm_job_id="1"),
            sequence=serialized_sequence,
            shots=100,
            status="PENDING",
        )
        async with async_session() as session:
            session.add(job)
            await session.commit()
            await session.refresh(job)
        job_id = job.id

        async def do_schedule():
            async with async_session() as session:
                return await scheduler.get_next_job(session)

        with mock_munge_auth(app, uid=user_id):
            cancel_response, claimed = await asyncio.gather(
                client.post(f"/jobs/{job_id}/cancel"), do_schedule()
            )

        async with async_session() as session:
            job = (
                await session.execute(select(Job).where(Job.id == job_id))
            ).scalar_one()

        # The property the atomic UPDATEs exist to guarantee: a job the
        # scheduler is about to run can't silently flip to CANCELED, since
        # the cancellation worker never looks at CANCELED jobs again.
        assert not (job.status == "CANCELED" and job.scheduled_at is not None)

        if claimed is not None:
            assert job.scheduled_at is not None
        if cancel_response.status_code == 200:
            assert job.canceled_at is not None

        # Terminal, so the next iteration's candidate pick can't see it.
        async with async_session() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(status="DONE")
            )
            await session.commit()


@pytest.mark.asyncio
async def test_repeated_session_revoke_and_scheduler_pick_race(
    client, app, serialized_sequence: str
):
    """Assert racing a real session revoke against a real scheduler pick
    never lets a job end up CANCELED and scheduled at once
    """
    user_id = 1000
    async_session = app.state.db_session_factory
    scheduler = schedulers[SchedulerStrategy.FIFO]

    for _ in range(40):
        session_record = Session(user_id=str(user_id), slurm_job_id="1")
        job = Job(
            session=session_record,
            sequence=serialized_sequence,
            shots=100,
            status="PENDING",
        )
        async with async_session() as session:
            session.add(job)
            await session.commit()
            await session.refresh(job)
        job_id = job.id
        session_id = session_record.id

        async def do_schedule():
            async with async_session() as session:
                return await scheduler.get_next_job(session)

        with mock_munge_auth(app, uid=0):
            revoke_response, claimed = await asyncio.gather(
                client.delete(f"/sessions/{session_id}"), do_schedule()
            )

        assert revoke_response.status_code == 200

        async with async_session() as session:
            job = (
                await session.execute(select(Job).where(Job.id == job_id))
            ).scalar_one()

        assert not (job.status == "CANCELED" and job.scheduled_at is not None)

        if claimed is not None:
            assert job.scheduled_at is not None

        # Terminal, so the next iteration's candidate pick can't see it.
        async with async_session() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(status="DONE")
            )
            await session.commit()


##########################################################################
############################# Timed testing  #############################
##########################################################################


class _HookedUpdateDBSession:
    """Session proxy running `hook` once, right before the first `UPDATE`.

    Passed to `get_next_job`, this lands the hook in the candidate-pick ->
    claim window: whatever reads a strategy does to pick a candidate, the
    claim itself has to be a write, so triggering on the first `UPDATE`
    (rather than on a fixed call count) keeps this test working regardless
    of how many reads a strategy's candidate pick does.
    """

    def __init__(self, session: AsyncSession, hook):
        self._session = session
        self._hook = hook

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def execute(self, statement, *args, **kwargs):
        if self._hook is not None and isinstance(statement, Update):
            hook, self._hook = self._hook, None
            await hook()
        return await self._session.execute(statement, *args, **kwargs)


@pytest.mark.asyncio
async def test_cancel_racing_scheduler_pick_is_not_claimed(
    client, app, serialized_sequence: str
):
    """Assert a cancel committed mid-pick stops the scheduler claiming the job

    1. Create a PENDING job for a given user
    2. Run the scheduler, cancelling the job via the API in the pick -> claim
       window (i.e. after the candidate is chosen, before it is claimed)
    3. Assert the scheduler claims nothing: its UPDATE re-checks `status`
       against the live row, which is now CANCELED
    4. Assert the job is CANCELED and never got a `scheduled_at`

    A job that is both CANCELED and scheduled is the state this must never
    reach: the cancellation worker only picks up PENDING/RUNNING jobs, so the
    QPU run would keep going with nothing left to stop it.
    """
    user_id = 1000
    job = Job(
        session=Session(user_id=str(user_id), slurm_job_id="1"),
        sequence=serialized_sequence,
        shots=100,
        status="PENDING",
    )
    async_session = app.state.db_session_factory

    async with async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)

    job_id = job.id

    async def cancel_mid_pick():
        with mock_munge_auth(app, uid=user_id):
            response = await client.post(f"/jobs/{job_id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELED"

    scheduler = schedulers[SchedulerStrategy.FIFO]
    async with async_session() as session:
        claimed = await scheduler.get_next_job(
            cast(AsyncSession, _HookedUpdateDBSession(session, cancel_mid_pick))
        )

    assert claimed is None

    async with async_session() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()

    assert job.status == "CANCELED"
    assert job.canceled_at is not None
    assert job.scheduled_at is None


@pytest.mark.asyncio
async def test_session_revoke_racing_scheduler_pick_is_not_claimed(
    client, app, serialized_sequence: str
):
    """Assert a session revoke committed mid-pick stops the scheduler
    claiming the job

    Same forced interleaving as `test_cancel_racing_scheduler_pick_is_not_claimed`,
    but through `DELETE /sessions/{id}` (bulk-cancels a session's jobs)
    instead of `POST /jobs/{id}/cancel`.
    """
    user_id = 1000
    session_record = Session(user_id=str(user_id), slurm_job_id="1")
    job = Job(
        session=session_record,
        sequence=serialized_sequence,
        shots=100,
        status="PENDING",
    )
    async_session = app.state.db_session_factory

    async with async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)

    job_id = job.id
    session_id = session_record.id

    async def revoke_mid_pick():
        with mock_munge_auth(app, uid=0):
            response = await client.delete(f"/sessions/{session_id}")
        assert response.status_code == 200

    scheduler = schedulers[SchedulerStrategy.FIFO]
    async with async_session() as session:
        claimed = await scheduler.get_next_job(
            cast(AsyncSession, _HookedUpdateDBSession(session, revoke_mid_pick))
        )

    assert claimed is None

    async with async_session() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()

    assert job.status == "CANCELED"
    assert job.canceled_at is not None
    assert job.scheduled_at is None
