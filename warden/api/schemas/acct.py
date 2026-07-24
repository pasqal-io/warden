from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from warden.api.schemas.common import JobID, SessionID, UserID


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
    total_duration: int


class JobsSummary(BaseModel):
    count: int = Field(0, ge=0)
    stats: list[JobSummaryStats] = Field(default_factory=list)


class AcctData(BaseModel):
    user_id: UserID
    sessions: SessionsSummary
    jobs: JobsSummary


class AcctUserData(BaseModel):
    pass


class SessionsData(BaseModel):
    id: SessionID
    user_id: UserID
    created_at: datetime
    revoked_at: datetime | None
    slurm_job_id: str


class JobData(BaseModel):
    id: JobID
    user_id: UserID
    session_id: SessionID
    execution_time: int
    status: str


# Common parameters for request and response
class AcctRequest(BaseModel):
    # Time filtering
    start_datetime: datetime
    end_datetime: datetime | None = Field(default=None)
    # Pagination
    limit: int = Field(100, gt=0, le=100)
    offset: int = Field(0, ge=0)


class AcctResponse(BaseModel):
    data: Any
    pagination: PaginationResponse


# Routes


# GET /accounting
class GetAcctRequest(AcctRequest):
    user_ids: list[UserID] | None = Field(default=None)


class GetAcctResponse(AcctResponse):
    data: list[AcctData]


# GET /accounting/user/{user_id}
class GetAcctUserRequest(AcctRequest):
    pass


class GetAcctUserResponse(AcctResponse):
    pass


# GET /accounting/jobs
class GetAcctJobsRequest(AcctRequest):
    session_id: SessionID | None
    user_id: UserID | None


class GetAcctJobsResponse(AcctResponse):
    data: list[JobData]
