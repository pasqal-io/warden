from datetime import datetime

from pydantic import BaseModel

from warden.api.schemas.common import JobID, SessionID, UserID


class CurrentJob(BaseModel):
    id: JobID
    session_id: SessionID
    user_id: UserID
    started_at: datetime | None
    backend_id: str | None


class OpenSession(BaseModel):
    id: SessionID
    user_id: UserID
    created_at: datetime
    slurm_job_id: str


class StatusResponse(BaseModel):
    pending_jobs_count: int
    current_job: CurrentJob | None
    open_sessions: list[OpenSession]
