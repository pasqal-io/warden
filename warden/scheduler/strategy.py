"""Queuing strategies"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Select, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.lib.config import SchedulerStrategy
from warden.lib.models import Job


class Scheduler(ABC):
    @staticmethod
    @abstractmethod
    def _select_next_job_stmt(session: AsyncSession) -> Select[tuple[Job]]:
        """Return select query for next job scheduling"""
        pass

    async def get_next_job(self, session: AsyncSession) -> Optional[Job]:
        """Return next job to run"""
        stmt = self._select_next_job_stmt(session)
        res = await session.execute(stmt.with_for_update(of=Job))
        job = res.scalar_one_or_none()
        if job:
            job.scheduled_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(job)
        return job


class FifoScheduler(Scheduler):
    @staticmethod
    def _select_next_job_stmt(session: AsyncSession) -> Select[tuple[Job]]:
        stmt = (
            select(Job)
            .where(Job.status.in_(["PENDING", "RUNNING"]))
            .order_by(
                # Rank jobs with an assigned backend before pending ones without
                case((Job.backend_id.is_(None), 1), else_=0),
                Job.backend_id.asc(),
                Job.created_at,
                Job.id,
            )
            .limit(1)
        )
        return stmt


schedulers = {SchedulerStrategy.FIFO: FifoScheduler()}
