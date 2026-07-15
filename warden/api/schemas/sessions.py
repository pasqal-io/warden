from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field

from warden.api.schemas.common import SessionID, UserID
from warden.lib.models.sessions import Session


class CreateSession(BaseModel):
    user_id: str
    scheduler_job_id: str = Field(
        validation_alias=AliasChoices("scheduler_job_id", "slurm_job_id")
    )
    qpu_slots: int = Field(default=1, ge=1)


class SessionResponse(BaseModel):
    id: SessionID
    user_id: UserID
    scheduler_job_id: str
    created_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None
    idle_expires_at: datetime
    expires_at: datetime
    qpu_slots: int

    @classmethod
    def from_model(cls, session: Session) -> "SessionResponse":
        return cls(
            id=session.id,
            user_id=session.user_id,
            scheduler_job_id=session.scheduler_job_id,
            created_at=session.created_at,
            revoked_at=session.revoked_at,
            revocation_reason=session.revocation_reason,
            idle_expires_at=session.idle_expires_at,
            expires_at=session.expires_at,
            qpu_slots=session.qpu_slots,
        )
