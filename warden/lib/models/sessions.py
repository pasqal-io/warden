import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    UUID as UUIDType,
)
from sqlalchemy import (
    DateTime,
    String,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from warden.lib.db.database import Base
from warden.lib.db.functions import duration_seconds


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

    @hybrid_property
    def duration(self):
        if self.revoked_at is None:
            return None
        return (self.revoked_at - self.created_at).total_seconds()

    @duration.inplace.expression
    @classmethod
    def _duration_expression(cls):
        """SQL expression: seconds between created_at and revoked_at (NULL if active)."""
        return duration_seconds(cls.created_at, cls.revoked_at)
