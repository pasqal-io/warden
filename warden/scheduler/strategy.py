"""Queuing strategies"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.lib.config import SchedulerStrategy
from warden.lib.models import Job, Session
from warden.lib.models.sessions import active_session_filter


class Scheduler(ABC):
    @staticmethod
    @abstractmethod
    async def get_next_job(session: AsyncSession) -> Optional[Job]:
        """Return next job to run"""
        pass


class FifoScheduler(Scheduler):
    @staticmethod
    async def get_next_job(session: AsyncSession) -> Optional[Job]:
        stmt = (
            select(Job)
            .join(Session)
            .where(
                Job.status.in_(["PENDING", "RUNNING"]),
                active_session_filter(),
            )
            .order_by(
                # Rank jobs with an assigned backend before pending ones without
                case((Job.backend_id.is_(None), 1), else_=0),
                Session.scheduler_vruntime,
                Job.backend_id.asc(),
                Job.created_at,
                Job.id,
            )
            .limit(1)
            .with_for_update(of=[Job, Session])
        )
        res = await session.execute(stmt)
        job = res.scalar_one_or_none()
        if job:
            if job.backend_id is None:
                job.session.scheduler_vruntime += 1 / job.session.qpu_slots
            job.scheduled_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(job)
        return job


schedulers = {SchedulerStrategy.FIFO: FifoScheduler()}
