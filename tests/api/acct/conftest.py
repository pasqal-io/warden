from datetime import datetime, timedelta
from typing import Sequence

import pytest

from warden.lib.models import Job, Session

ACCT_ENDPOINT = "/accounting"
ACCT_SESSIONS_ENDPOINT = "/accounting/sessions"
ACCT_JOBS_ENDPOINT = "/accounting/jobs"
ACCT_ENDPOINTS = [ACCT_ENDPOINT, ACCT_JOBS_ENDPOINT, ACCT_SESSIONS_ENDPOINT]


async def acct_populate_db(
    app,
    n_users: int,
    first_session_start: datetime = datetime(2026, 1, 1, 0, 0, 0),
    session_duration: timedelta = timedelta(hours=1),
    user_time_offset: timedelta = timedelta(hours=1),
    job_statuses: Sequence[str] = ("DONE",),
    job_wait_time: timedelta = timedelta(seconds=15),
    job_execution_time: timedelta = timedelta(seconds=45),
    job_shots: int = 100,
) -> tuple[list[str], list[Job], list[Session]]:
    """Creates mock data for accounting testing in DB

    One session per user, and one job per entry in `job_statuses` per user.
    Passing several statuses makes the jobs aggregation produce more rows than
    the sessions aggregation, which is what exercises their pagination.
    """
    BASE_START_DATETIME = first_session_start
    BASE_END_DATETIME = BASE_START_DATETIME + session_duration
    user_uids = [str(i) for i in range(9000, 9000 + n_users)]

    # Create at least one session and job per user
    sessions = []
    jobs = []
    for i, uid in enumerate(user_uids):
        session_start = BASE_START_DATETIME + i * user_time_offset
        session_end = BASE_END_DATETIME + i * user_time_offset

        job_created = session_start
        job_started = session_start + job_wait_time
        job_ended = job_started + job_execution_time

        sessions.append(
            Session(
                created_at=session_start,
                revoked_at=session_end,
                user_id=uid,
                slurm_job_id=str(i),
            )
        )
        for status in job_statuses:
            jobs.append(
                Job(
                    status=status,
                    logs="",
                    shots=job_shots,
                    sequence="",
                    created_at=job_created,
                    scheduled_at=job_started,
                    started_at=job_started,
                    ended_at=job_ended,
                    # Relationship
                    session=sessions[-1],
                )
            )

    async_session_factory = app.state.db_session_factory
    async with async_session_factory() as db_session:
        db_session.add_all(sessions)
        db_session.add_all(jobs)
        await db_session.commit()
    return user_uids, jobs, sessions


@pytest.fixture(scope="session", params=ACCT_ENDPOINTS)
def accounting_endpoint(request):
    return request.param
