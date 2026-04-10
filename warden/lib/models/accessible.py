from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from warden.lib.db.database import Base


class AccessibilitySettings(Base):
    __tablename__ = "accessibility_settings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Auto-incrementing ID for each change",
    )
    is_accessible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Status of Warden accessibility for receiving new jobs",
    )
    message: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Warden ok.",
        doc="Document the reason for (in)accessibility of Warden",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        doc="Accessibility update timestamp",
    )
