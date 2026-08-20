"""Session revocation logic shared by the API and the scheduler."""

from datetime import datetime, timezone
from logging import getLogger

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.lib.models import Job, Session

logger = getLogger(__name__)


async def revoke_session_and_cancel_jobs(
    db_session: AsyncSession, session_record: Session
) -> None:
    """Revoke a session and cancel every non-terminal job attached to it."""
    session_record.revoked_at = datetime.now(timezone.utc)
    await db_session.flush()
    await db_session.commit()

    async with db_session.begin():
        result = await db_session.execute(
            select(Job)
            .where(
                Job.session_id == session_record.id,
                Job.status.not_in(("ERROR", "DONE", "CANCELED")),
                Job.canceled_at.is_(None),
            )
            .with_for_update(of=Job)
        )
        jobs_to_cancel = result.scalars()
        for job in jobs_to_cancel:
            logger.info(
                "Cancelling job '%s' attached to session %s", job.id, session_record.id
            )
            job.canceled_at = datetime.now(timezone.utc)
            # Not yet started by the worker
            if job.scheduled_at is None:
                # Set job to cancel
                job.status = "CANCELED"
            # Releases nowait
