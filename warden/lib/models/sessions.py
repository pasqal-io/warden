import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import (
    UUID as UUIDType,
)
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from warden.lib.db.database import Base
from warden.lib.db.functions import duration_seconds


class QPUCapacityLock(Base):
    """Provide one database row for serializing QPU capacity changes."""

    __tablename__ = "qpu_capacity_lock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        UUIDType,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduler_job_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        doc="ID of the scheduler job which created this session.",
    )
    qpu_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scheduler_vruntime: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    idle_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc) + timedelta(hours=1),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=30),
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    @hybrid_property
    def duration(self):
        """Seconds between created_at and revoked_at (rounded to the nearest
        second to match duration_seconds), or None while the session is active."""
        if self.revoked_at is None:
            return None
        return round((self.revoked_at - self.created_at).total_seconds())

    @duration.inplace.expression
    @classmethod
    def _duration_expression(cls):
        """SQL expression: seconds between created_at and revoked_at (NULL if active)."""
        return duration_seconds(cls.created_at, cls.revoked_at)


def active_session_filter() -> ColumnElement[bool]:
    return Session.revoked_at.is_(None)
