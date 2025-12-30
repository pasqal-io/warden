from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    UUID,
    String,
    DateTime,
)
from warden.db.database import Base
from sqlalchemy.orm import Mapped, mapped_column


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        UUID,
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
        String, doc="ID of the slurm job which created this session."
    )
