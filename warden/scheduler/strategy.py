"""Queuing strategies"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, cast

from sqlalchemy import CursorResult, case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from warden.lib.config import SchedulerStrategy
from warden.lib.models import Job

SCHEDULABLE_STATUS = ["PENDING", "RUNNING"]


class Scheduler(ABC):
    @staticmethod
    @abstractmethod
    async def _get_next_job_id(session: AsyncSession) -> Optional[int]:
        """Return ID of next job, where each implementatino define it's strategy"""
        pass

    async def get_next_job(self, session: AsyncSession) -> Optional[Job]:
        """Tries to 'acquire' the job to schedule by setting `scheduler_at` in db.
        Then returns job record to schedule on the qpu"""
        candidate_id = await self._get_next_job_id(session)
        if candidate_id is None:
            return None

        # Atomic claim: the status check is re-evaluated against the live
        # row by this single UPDATE, so a job canceled concurrently between
        # the candidate lookup above and this write can't get claimed here.
        result = cast(
            CursorResult,
            await session.execute(
                update(Job)
                .where(Job.id == candidate_id, Job.status.in_(SCHEDULABLE_STATUS))
                .values(scheduled_at=datetime.now(timezone.utc))
            ),
        )
        await session.commit()
        if result.rowcount == 0:
            # where clause had 0 match, candidate job was canceled concurrently
            return None

        return await session.get(Job, candidate_id)


class FifoScheduler(Scheduler):
    """Simple FIFO Queue"""

    @staticmethod
    async def _get_next_job_id(session: AsyncSession) -> Optional[int]:
        candidate_stmt = (
            select(Job.id)
            .where(Job.status.in_(SCHEDULABLE_STATUS))
            .order_by(
                # Rank jobs with an assigned backend before pending ones without
                case((Job.backend_id.is_(None), 1), else_=0),
                Job.backend_id.asc(),
                Job.created_at,
                Job.id,
            )
            .limit(1)
        )
        return (await session.execute(candidate_stmt)).scalar_one_or_none()


schedulers = {SchedulerStrategy.FIFO: FifoScheduler()}
