"""Useful data types for QPU API parsing"""

from dataclasses import replace
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
    logs: str | None = None

    def to_error(self) -> "QPUJobInfo":
        """Returns a copy of qpu_job with status attribute set to ERROR"""
        return replace(self, status="ERROR")

    def set_logs(self, logs: str) -> "QPUJobInfo":
        """Returns a copy of qpu_job with logs attribute set to provided logs"""
        return replace(self, logs=logs)


@dataclass
class QPUOperationalStatus:
    operational_status: QPUStatus | None = None


@dataclass
class QPUInfo:
    specs: Any | None = None
