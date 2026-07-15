"""Useful data types for QPU API parsing"""

from datetime import datetime, timezone
from typing import Annotated, Literal, TypeAlias

from pydantic import AfterValidator
from pydantic.dataclasses import dataclass


def _as_utc(value: datetime | None) -> datetime | None:
    """Ensure a datetime is UTC-aware. Naive datetimes from the API are assumed UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UTCDatetime = Annotated[datetime, AfterValidator(_as_utc)]

JobStatus: TypeAlias = Literal["PENDING", "RUNNING", "ERROR", "CANCELED", "DONE"]
QPUStatus: TypeAlias = Literal["UP", "DOWN"]


@dataclass(frozen=True)
class QPUJobInfo:
    uid: int
    batch_id: str | None
    status: JobStatus | None
    result: str | None
    program_id: int | None
    created_datetime: UTCDatetime
    start_datetime: UTCDatetime | None
    end_datetime: UTCDatetime | None


@dataclass
class QPUOperationalStatus:
    operational_status: QPUStatus | None = None


@dataclass
class QPUInfo:
    specs: dict | None = None
