from datetime import datetime

from pydantic import BaseModel

from warden.lib.models.jobs import Job


class JobCreate(BaseModel):
    sequence: str
    shots: int


class JobResponse(BaseModel):
    id: int
    user_id: str
    created_at: datetime
    status: str
    results: str | None

    @classmethod
    def from_model(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
            user_id=job.user_id,
            created_at=job.created_at,
            status=job.status,
            results=job.results,
        )
