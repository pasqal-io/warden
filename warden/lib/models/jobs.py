from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from warden.lib.db.database import Base
from warden.lib.db.functions import duration_seconds
from warden.lib.models.sessions import Session


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        doc="Warden ID of the job.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        doc="Datetime when the job was received by warden.",
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Datetime when the job was scheduled by the warden scheduler.",
    )
    canceled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Datetime when the first request to cancel the job was received by the warden api.",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Datetime when the job was started by the QPU.",
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Datetime when the job's processing was over.",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="PENDING",
        doc="Status of the job.",
    )
    logs: Mapped[str | None] = mapped_column(
        Text().with_variant(Text(16777215), "mysql"),
        nullable=False,
        server_default="",
        doc="Logs associated with the job execution.",
    )
    shots: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Number of bitstrings the QPU should return.",
    )
    sequence: Mapped[str] = mapped_column(
        Text,
        doc="Serialized pulser sequence to execute on the QPU.",
    )
    backend_id: Mapped[str | None] = mapped_column(
        String(255),
        default=None,
        doc="ID of the job assigned by the QPU.",
    )
    results: Mapped[str | None] = mapped_column(
        Text().with_variant(Text(16777215), "mysql"),
        nullable=True,
        doc="Serialized results from the QPU.",
    )
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, default=None
    )
    session: Mapped[Session] = relationship("Session", lazy="joined")

    user_id: AssociationProxy[str] = association_proxy(
        "session",
        "user_id",
    )

    @hybrid_property
    def effective_end(self):
        """ended_at, or canceled_at if the job was canceled before ended_at
        was recorded."""
        return self.ended_at or self.canceled_at

    @effective_end.inplace.expression
    @classmethod
    def _effective_end_expression(cls):
        return func.coalesce(cls.ended_at, cls.canceled_at)

    @hybrid_property
    def execution_time(self):
        """Seconds from started_at to effective_end (rounded to the nearest
        second to match duration_seconds), or None if either is unset."""
        if self.started_at is None or self.effective_end is None:
            return None
        return round((self.effective_end - self.started_at).total_seconds())

    @execution_time.inplace.expression
    @classmethod
    def _execution_time_expression(cls):
        """SQL expression: seconds from started_at to effective_end."""
        return duration_seconds(cls.started_at, cls.effective_end)

    @hybrid_property
    def wait_time(self):
        """Seconds from created_at to started_at (rounded to the nearest second
        to match duration_seconds), or None if not started yet."""
        if self.started_at is None:
            return None
        return round((self.started_at - self.created_at).total_seconds())

    @wait_time.inplace.expression
    @classmethod
    def _wait_time_expression(cls):
        """SQL expression: seconds from created_at to started_at."""
        return duration_seconds(cls.created_at, cls.started_at)
