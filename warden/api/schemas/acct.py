from datetime import datetime
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, Field

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


class JobsSummary(BaseModel):
    count: int = Field(default=0, ge=0)
    execution_time: int = Field(default=0, ge=0)
    wait_time: int = Field(default=0, ge=0)
    stats: list[JobSummaryStats] = Field(default_factory=list)


class AcctData(BaseModel):
    user_id: UserID
    sessions: SessionsSummary
    jobs: JobsSummary


class AcctUserData(BaseModel):
    pass


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


# Common parameters for request and response
class AcctRequest(BaseModel):
    # User filtering
    user_ids: list[UserID] | None = Field(default=None)
    # Time filtering
    start_datetime: datetime
    end_datetime: datetime | None = Field(default=None)
    # Pagination
    limit: int = Field(default=100, gt=0, le=100)
    offset: int = Field(default=0, ge=0)


class AcctResponse(BaseModel):
    data: Any
    pagination: PaginationResponse


# Routes


# GET /accounting
class GetAcctRequest(AcctRequest):
    pass


class GetAcctResponse(AcctResponse):
    data: list[AcctData]


GetAcctRequestQueryParams = Annotated[GetAcctRequest, Query()]


# GET /accounting/sessions
class GetAcctSessionsRequest(AcctRequest):
    slurm_job_id: str | None = Field(default=None)


class GetAcctSessionsResponse(AcctResponse):
    data: list[SessionData]


GetAcctSessionsRequestQueryParams = Annotated[GetAcctSessionsRequest, Query()]


# GET /accounting/jobs
class GetAcctJobsRequest(AcctRequest):
    session_id: SessionID | None = Field(default=None)
    status: str | None = Field(default=None)


class GetAcctJobsResponse(AcctResponse):
    data: list[JobData]


GetAcctJobsRequestQueryParams = Annotated[GetAcctJobsRequest, Query()]
