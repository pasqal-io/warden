import asyncio
from datetime import datetime
from typing import TypeAlias

from pydantic.dataclasses import dataclass

from warden.lib.qpu_client.types import JobStatus


@dataclass
class JobUpdate:
    """Communication object between worker and db update task"""

    status: JobStatus
    new_logs: str
    backend_id: str | None = None
    result: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


JobUpdateQueue: TypeAlias = asyncio.Queue[JobUpdate]
