import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    UUID as UUIDType,
)
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from warden.lib.db.database import Base


class QPUCapacityLock(Base):
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
    slurm_job_id: Mapped[str] = mapped_column(
        String(255), doc="ID of the slurm job which created this session."
    )
    qpu_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scheduler_vruntime: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )


def active_session_filter() -> ColumnElement[bool]:
    return Session.revoked_at.is_(None)
