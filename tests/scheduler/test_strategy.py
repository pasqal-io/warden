"""Testing warden.scheduler.strategy"""

import pytest
from datetime import datetime, timedelta

from warden.lib.models import Job, Session

from warden.scheduler.strategy import schedulers


@pytest.mark.asyncio
async def test_fifo_nominal(db_session_maker):
    """Testing FIFO scheduler strategy nominal behavior"""
    scheduler = schedulers["FIFO"]
    now = datetime.now()

    jobs = [
        Job(
            id=1,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=1),
        ),
        Job(
            id=2,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=0),
        ),
        Job(
            id=3,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=3),
        ),
        Job(
            id=4,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=2),
        ),
    ]

    async with db_session_maker() as session:
        session.add_all(jobs)
        await session.commit()

    schedule = []
    async with db_session_maker() as session:
        for _ in range(5):
            next_job = await scheduler.get_next_job(session)
            # Mock the execution of the scheduled job
            if next_job:
                next_job.status = "DONE"
                await session.commit()
            schedule.append(next_job)

        assert len(schedule) == 5
        assert schedule[0].id == 2
        assert schedule[1].id == 1
        assert schedule[2].id == 4
        assert schedule[3].id == 3
        assert schedule[4] is None

@pytest.mark.asyncio
async def test_fifo_id_precedence(db_session_maker):
    """Testing FIFO scheduler with ID sorting if same datetime"""
    schdeduler = schedulers["FIFO"]
    now = datetime.now()

    jobs = [
        Job(
            id=1,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=1),
        ),
        Job(
            id=2,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=0),
        ),
        Job(
            id=3,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=0),
        ),
        Job(
            id=4,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=2),
        ),
    ]

    async with db_session_maker() as session:
        session.add_all(jobs)
        await session.commit()

    schedule = []
    async with db_session_maker() as session:
        for _ in range(5):
            next_job = await schdeduler.get_next_job(session)
            # Mock the execution of the scheduled job
            if next_job:
                next_job.status = "DONE"
                await session.commit()
            schedule.append(next_job)

        assert len(schedule) == 5
        assert schedule[0].id == 2
        assert schedule[1].id == 3
        assert schedule[2].id == 1
        assert schedule[3].id == 4
        assert schedule[4] is None

@pytest.mark.asyncio
async def test_fifo_job_running(db_session_maker):
    """Testing FIFO scheduler strategy with job already in running state"""
    schdeduler = schedulers["FIFO"]
    now = datetime.now()

    jobs = [
        Job(
            id=1,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            backend_id=2,
            created_at=now + timedelta(seconds=1),
        ),
        Job(
            id=2,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=3),
        ),
        Job(
            id=3,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="PENDING",
            created_at=now + timedelta(seconds=2),
        ),
        Job(
            id=4,
            session=Session(slurm_job_id=1, user_id="1000"),
            shots=100,
            sequence="{}",
            status="RUNNING",
            backend_id=1,
            created_at=now + timedelta(seconds=1),
        ),
    ]

    async with db_session_maker() as session:
        session.add_all(jobs)
        await session.commit()

    schedule = []
    async with db_session_maker() as session:
        for _ in range(5):
            next_job = await schdeduler.get_next_job(session)
            # Mock the execution of the scheduled job
            if next_job:
                next_job.status = "DONE"
                await session.commit()
            schedule.append(next_job)

        assert len(schedule) == 5
        assert schedule[0].id == 4
        assert schedule[1].id == 1
        assert schedule[2].id == 3
        assert schedule[3].id == 2
        assert schedule[4] is None
