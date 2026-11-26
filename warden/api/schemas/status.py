from datetime import datetime
from typing import Literal

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


class ResourceCapacity(BaseModel):
    available_slots: int
    max_slots: int


class StatusSummaryResponse(BaseModel):
    """Mirrors QRMI's `ResourceStatus`, so the client maps it field by field."""

    status: Literal["online", "offline", "paused"]
    status_reason: str | None
    healthy: bool | None
    busy: bool
    pending_job_count: int
    capacity: ResourceCapacity | None


class StatusResponse(StatusSummaryResponse):
    """Admin view: the public resource status plus live jobs and sessions."""

    current_job: CurrentJob | None
    open_sessions: list[OpenSession]
