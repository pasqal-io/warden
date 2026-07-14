from datetime import datetime

from pydantic import BaseModel, Field

from warden.api.schemas.common import SessionID, UserID
from warden.lib.models.sessions import Session


class CreateSession(BaseModel):
    user_id: str
    slurm_job_id: str
    qpu_slots: int = Field(default=1, ge=1)


class SessionResponse(BaseModel):
    id: SessionID
    user_id: UserID
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
