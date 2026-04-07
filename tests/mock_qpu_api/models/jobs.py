from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class JobStatus(Enum):
    """The list of the possible job status."""

    # The Job has been created
    PENDING = "PENDING"
    # The job is running on the QPU.
    RUNNING = "RUNNING"
    # The job is stopped because an error occurred.
    ERROR = "ERROR"
    # The job is canceled.
    CANCELED = "CANCELED"
    # The job ended successfully.
    DONE = "DONE"


class Context(BaseModel):
    batch_id: str | None
    pasqman_job_id: str | None


class Job(BaseModel):
    uid: int
    datetime: "datetime"

    nb_run: int

    pulser_sequence: str
    result: str | None = None

    client_id: int | None = None

    program_id: int | None = None
    # TODO: check but not needed
    program: Any | None = None

    context: Context | None = None
    batch_id: str | None = None

    status: JobStatus

    created_datetime: Optional["datetime"] = None
    start_datetime: Optional["datetime"] = None
    end_datetime: Optional["datetime"] = None

    progress: dict[str, Any] | None = None


class JobCreation(BaseModel):
    nb_run: int
    pulser_sequence: str
    context: Context
