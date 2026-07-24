"""Useful data types for QPU API parsing"""

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic.dataclasses import dataclass

JobStatus: TypeAlias = Literal["PENDING", "RUNNING", "ERROR", "CANCELED", "DONE"]
QPUStatus: TypeAlias = Literal["UP", "DOWN"]


@dataclass
class QPUJobInfo:
    uid: int
    batch_id: str | None
    status: JobStatus | None
    result: str | None
    program_id: int | None
    created_datetime: datetime
    start_datetime: datetime | None
    end_datetime: datetime | None


@dataclass
class QPUOperationalStatus:
    operational_status: QPUStatus | None = None


@dataclass
class QPUInfo:
    specs: dict | None = None
