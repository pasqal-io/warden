"""Common queries shared across Warden components."""

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.lib.models import AccessibilitySettings, Job


async def get_latest_accessibility_settings(
    db_session: AsyncSession,
) -> AccessibilitySettings:
    """Get the most recent accessibility settings record in db"""
    result = await db_session.execute(
        select(AccessibilitySettings).order_by(desc(AccessibilitySettings.id)).limit(1)
    )
    settings = result.scalar_one_or_none()

    if settings is None:
        # Create initial record with default behavior
        settings = AccessibilitySettings()
        db_session.add(settings)
        await db_session.commit()
        await db_session.refresh(settings)

    return settings


async def count_jobs(db_session: AsyncSession, status: str) -> int:
    """Number of jobs in the given status."""
    return (
        await db_session.scalar(select(func.count(Job.id)).where(Job.status == status))
        or 0
    )
