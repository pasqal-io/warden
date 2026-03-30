from datetime import datetime

from pydantic import UUID4, BaseModel

from warden.lib.models.sessions import Session


class CreateSession(BaseModel):
    user_id: str
    slurm_job_id: str


class SessionResponse(BaseModel):
    id: UUID4
    user_id: str
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_model(cls, session: Session) -> "SessionResponse":
        return cls(
            id=session.id,
            user_id=session.user_id,
            created_at=session.created_at,
            revoked_at=session.revoked_at,
        )
