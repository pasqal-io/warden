"""Queuing strategies"""

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.lib.models import Job


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
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


schedulers = {"FIFO": FifoScheduler()}
