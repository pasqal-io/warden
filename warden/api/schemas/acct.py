from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from warden.api.schemas.common import JobID, SessionID, UserID
from warden.lib.models import Session
from warden.lib.qpu_client.types import JobStatus


class PaginationResponse(BaseModel):
    total: int
    start: int
    end: int

    @classmethod
    def for_page(cls, *, offset: int, count: int, total: int) -> "PaginationResponse":
        """Pagination for a page holding ``count`` items starting at ``offset``.

        ``start`` is clamped to ``total`` so it never points beyond the data
        (e.g. an offset past the end), which keeps the invariant
        ``start <= end <= total`` and ``end - start == count``.
        """
        start = min(offset, total)
        return cls(total=total, start=start, end=start + count)


class SessionsSummary(BaseModel):
    count: int
    total_duration: int


class JobSummaryStats(BaseModel):
    count: int
    execution_time: int
    wait_time: int
    shots: int


class JobsSummary(BaseModel):
    count: int = Field(default=0, ge=0)
    execution_time: int = Field(default=0, ge=0)
    wait_time: int = Field(default=0, ge=0)
    shots: int = Field(default=0, ge=0)
    per_status: dict[JobStatus, JobSummaryStats] = Field(default_factory=dict)


class AcctData(BaseModel):
    user_id: UserID
    sessions: SessionsSummary
    jobs: JobsSummary


class SessionData(BaseModel):
    id: SessionID
    user_id: UserID
    created_at: datetime
    revoked_at: datetime | None
    slurm_job_id: str
    total_duration: int = Field(default=0, ge=0)
    jobs_count: int = Field(default=0, ge=0)

    @classmethod
    def from_session_record(cls, session: Session) -> "SessionData":
        return cls(
            id=session.id,
            user_id=session.user_id,
            created_at=session.created_at,
            revoked_at=session.revoked_at,
            slurm_job_id=session.slurm_job_id,
        )


class JobData(BaseModel):
    id: JobID
    user_id: UserID
    session_id: SessionID
    slurm_job_id: str
    status: JobStatus
    shots: int
    execution_time: int
    wait_time: int


# Base models for accounting requests and responses
class AcctRequest(BaseModel):
    # Reject unknown query params instead of silently ignoring them
    model_config = ConfigDict(extra="forbid")

    # User filtering
    user_id: list[UserID] = Field(
        default_factory=list,
        description="Restrict the report to these user IDs. Unset returns all users.",
    )
    # Time filtering on the sessions revoked_at field
    ended_after: datetime | None = Field(
        default=None,
        description=(
            "Only include data from records that ended at or after this datetime. "
            "Naive datetimes are assumed to be UTC."
        ),
    )
    ended_before: datetime | None = Field(
        default=None,
        description=(
            "Only include data from records that ended strictly before this datetime. "
            "Unset means no upper bound."
            "Naive datetimes are assumed to be UTC."
        ),
    )
    # Pagination
    limit: int = Field(
        default=100,
        gt=0,
        le=100,
        description="Maximum number of rows to return.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of rows to skip, for pagination.",
    )

    @field_validator("ended_after", "ended_before")
    @classmethod
    def _to_utc(cls, value: datetime | None) -> datetime | None:
        """Normalize to UTC, since not all supported DB backends
        preserve tzinfo on the stored `DateTime(timezone=True)` columns
        but keep UTC tz info for postgres backend.

        Aware datetimes are converted to UTC and naive datetimes are assumed
        to already be UTC.
        """
        if value is None:
            return None
        elif value.tzinfo is None:
            # Assumed to be UTC
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class AcctResponse(BaseModel):
    data: Any
    pagination: PaginationResponse


# Routes


# GET /accounting
class GetAcctResponse(AcctResponse):
    data: list[AcctData]


GetAcctRequestQueryParams = Annotated[AcctRequest, Query()]


# GET /accounting/sessions
class GetAcctSessionsRequest(AcctRequest):
    slurm_job_id: list[str] = Field(
        default_factory=list,
        description="Restrict the report to these Slurm job IDs.",
    )

    session_id: list[SessionID] = Field(
        default_factory=list,
        description="Restrict the report to these session IDs.",
    )


class GetAcctSessionsResponse(AcctResponse):
    data: list[SessionData]


GetAcctSessionsRequestQueryParams = Annotated[GetAcctSessionsRequest, Query()]


# GET /accounting/jobs
class GetAcctJobsRequest(GetAcctSessionsRequest):
    status: list[JobStatus] = Field(
        default_factory=list,
        description="Restrict the report to jobs with these statuses.",
    )

    job_id: list[JobID] = Field(
        default_factory=list,
        description="Restrict the report to jobs with these IDs.",
    )


class GetAcctJobsResponse(AcctResponse):
    data: list[JobData]


GetAcctJobsRequestQueryParams = Annotated[GetAcctJobsRequest, Query()]
