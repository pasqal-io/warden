from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from warden.lib.models.sessions import Session


class CreateSession(BaseModel):
    user_id: str
    slurm_job_id: str
    qpu_slots: int = Field(default=1, ge=1)


class SessionResponse(BaseModel):
    id: UUID
    user_id: str
    created_at: datetime
    revoked_at: datetime | None
    qpu_slots: int

    @classmethod
    def from_model(cls, session: Session) -> "SessionResponse":
        return cls(
            id=session.id,
            user_id=session.user_id,
            created_at=session.created_at,
            revoked_at=session.revoked_at,
            qpu_slots=session.qpu_slots,
        )
