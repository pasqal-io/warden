"""Useful data types for QPU API parsing"""

from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic.dataclasses import dataclass

JobStatus: TypeAlias = Literal["PENDING", "RUNNING", "ERROR", "CANCELED", "DONE"]
QPUStatus: TypeAlias = Literal["UP", "DOWN"]


@dataclass(frozen=True)
class QPUJobInfo:
    uid: int | None = None
    batch_id: str | None = None
    status: JobStatus | None = None
    result: str | None = None
    program_id: int | None = None
    created_datetime: datetime | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None


@dataclass
class QPUOperationalStatus:
    operational_status: QPUStatus | None = None


@dataclass
class QPUInfo:
    specs: Any | None = None
