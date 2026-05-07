from datetime import datetime, timezone

from sqlalchemy import (
    UUID,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from warden.lib.db.database import Base
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
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="ID of the user who submitted the job.",
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
    results: Mapped[str | None] = Column(
        Text().with_variant(Text(16777215), "mysql"),
        nullable=True,
        doc="Serialized results from the QPU.",
    )
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, default=None
    )
    session: Mapped[Session] = relationship("Session", lazy="joined")

    user_id: AssociationProxy[UUID] = association_proxy(
        "session",
        "user_id",
    )
