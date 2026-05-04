import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from warden.lib.qpu_client.types import JobStatus


@dataclass(frozen=True)
class JobUpdate:
    """Communication object between worker and db update task"""

    status: JobStatus
    new_logs: str
    backend_id: int | None = None
    result: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


UpdateQueue: TypeAlias = asyncio.Queue[JobUpdate]
