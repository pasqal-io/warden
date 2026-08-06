from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, Field, field_validator

from warden.api.schemas.common import JobID, SessionID, UserID
from warden.lib.models import Session


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
    status: str
    count: int
    execution_time: int
    wait_time: int
    shots: int


class JobsSummary(BaseModel):
    count: int = Field(default=0, ge=0)
    execution_time: int = Field(default=0, ge=0)
    wait_time: int = Field(default=0, ge=0)
    shots: int = Field(default=0, ge=0)
    per_status: list[JobSummaryStats] = Field(default_factory=list)


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
    status: str
    shots: int
    execution_time: int
    wait_time: int


# Base models for accounting requests and responses
class AcctRequest(BaseModel):
    # User filtering
    user_ids: list[UserID] | None = Field(
        default=None,
        description="Restrict the report to these user IDs. Unset returns all users.",
        examples=[["1000", "1001"]],
    )
    # Time filtering on the sessions revoked_at field
    ended_after: datetime | None = Field(
        default=None,
        description=(
            "Only include data from sessions revoked at or after this datetime. "
            "Naive datetimes are assumed to be UTC."
        ),
        examples=["2026-07-01T00:00:00Z"],
    )
    ended_before: datetime | None = Field(
        default=None,
        description=(
            "Only include data from sessions revoked strictly before this datetime. "
            "Unset means no upper bound. Naive datetimes are assumed to be UTC."
        ),
        examples=["2026-07-29T00:00:00Z"],
    )
    # Pagination
    limit: int = Field(
        default=100,
        gt=0,
        le=100,
        description="Maximum number of rows to return.",
        examples=[50],
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of rows to skip, for pagination.",
        examples=[0],
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
    slurm_job_id: str | None = Field(
        default=None,
        description="Restrict the report to this Slurm job ID.",
        examples=["123456"],
    )


class GetAcctSessionsResponse(AcctResponse):
    data: list[SessionData]


GetAcctSessionsRequestQueryParams = Annotated[GetAcctSessionsRequest, Query()]


# GET /accounting/jobs
class GetAcctJobsRequest(AcctRequest):
    session_id: SessionID | None = Field(
        default=None,
        description="Restrict the report to this session ID.",
        examples=["b3f1c2d4-5678-90ab-cdef-1234567890ab"],
    )
    status: str | None = Field(
        default=None,
        description="Restrict the report to jobs with this status.",
        examples=["ERROR"],
    )


class GetAcctJobsResponse(AcctResponse):
    data: list[JobData]


GetAcctJobsRequestQueryParams = Annotated[GetAcctJobsRequest, Query()]
