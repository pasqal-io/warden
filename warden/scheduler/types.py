from dataclasses import dataclass
from datetime import datetime

from warden.lib.qpu_client.types import JobStatus


@dataclass(frozen=True)
class JobUpdate:
    status: JobStatus
    new_logs: str
    backend_id: int | None = None
    result: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
