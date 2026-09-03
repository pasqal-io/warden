"""Queuing strategies"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, cast

from sqlalchemy import CursorResult, case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from warden.lib.config import SchedulerStrategy
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
        candidate_stmt = (
            select(Job.id)
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
        candidate_id = (await session.execute(candidate_stmt)).scalar_one_or_none()
        if candidate_id is None:
            return None

        # Atomic claim: the status check is re-evaluated against the live
        # row by this single UPDATE, so a job canceled concurrently between
        # the candidate lookup above and this write can't get claimed here.
        result = cast(
            CursorResult,
            await session.execute(
                update(Job)
                .where(Job.id == candidate_id, Job.status.in_(["PENDING", "RUNNING"]))
                .values(scheduled_at=datetime.now(timezone.utc))
            ),
        )
        await session.commit()
        if result.rowcount == 0:
            # where clause had 0 match, candidate job was canceled concurrently
            return None

        return await session.get(Job, candidate_id)


schedulers = {SchedulerStrategy.FIFO: FifoScheduler()}
