from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote

import pytest

from tests.api.acct.conftest import ACCT_ENDPOINT, ACCT_JOBS_ENDPOINT, acct_populate_db
from tests.api.conftest import mock_munge_auth
from warden.api.schemas.acct import AcctRequest
from warden.lib.models import Job, Session

###############################################################################
############################### ACCT QUERY TESTS ##############################
###############################################################################


def test_acct_request_normalizes_datetimes_to_utc():
    """The `ended_after`/`ended_before` validator must produce UTC-aware
    values regardless of the offset supplied by the caller, since not every
    supported DB backend preserves timezone info on stored columns."""

    naive_utc = datetime(2026, 1, 1, 12, 0, 0)
    aware_utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    aware_non_utc = naive_utc.replace(tzinfo=timezone(timedelta(hours=2))) + timedelta(
        hours=2
    )

    req = AcctRequest(ended_after=aware_non_utc, ended_before=aware_non_utc)
    assert req.ended_after == aware_utc
    assert req.ended_before == aware_utc

    # Naive input is assumed to already be UTC and passed through unchanged.
    req_naive = AcctRequest(ended_after=naive_utc)
    assert req_naive.ended_after == aware_utc
    assert req_naive.ended_after is not None
    assert req_naive.ended_after.tzinfo is timezone.utc

    # ended_before is optional; None must pass through untouched.
    assert req_naive.ended_before is None


###############################################################################
############################## COMMON ROUTE TESTS #############################
###############################################################################


@pytest.mark.asyncio
async def test_acct_nominal_get_all(client, app, accounting_endpoint):
    """Test that accounting endpoints accept requests without any query parameter set"""

    N_USERS = 10
    assert N_USERS < AcctRequest.model_fields["limit"].default

    # One session/jobs per user to make test pass on all routes
    await acct_populate_db(app, N_USERS, job_statuses=("DONE",))

    with mock_munge_auth(app, uid=0):
        response = await client.get(accounting_endpoint)
    assert response.status_code == 200
    assert len(response.json()["data"]) == N_USERS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query, expected_start, expected_end, expected_len, expected_first_index",
    [
        ("limit=100", 0, 10, 10, 0),
        ("limit=5", 0, 5, 5, 0),
        ("limit=5&offset=4", 4, 9, 5, 4),
        ("offset=8", 8, 10, 2, 8),
        # Offset past the end: the page is empty, and start/end are clamped to
        # total so the response stays consistent (end - start == 0 items, never
        # pointing beyond the data).
        ("offset=20", 10, 10, 0, None),
    ],
)
async def test_acct_pagination(
    client,
    app,
    accounting_endpoint: str,
    query: Literal["limit=100", "limit=5", "limit=5&offset=4", "offset=8", "offset=20"],
    expected_start: Literal[0, 4, 8, 10],
    expected_end: Literal[10, 5, 9],
    expected_len: Literal[10, 5, 2, 0],
    expected_first_index: Literal[0, 4, 8] | None,
):
    """Assert that the accounting data query returns the right number of rows for each of the endpoints.

    We create 10 users, each with one session and one job in the session,
    - /accounting
    - /accounting/jobs
    - /accounting/sessions
    Then all have the same number of rows (10) so we can test their pagination similarly
    """
    N_USERS = 10
    assert N_USERS < AcctRequest.model_fields["limit"].default

    user_uids, _, _ = await acct_populate_db(app, N_USERS, job_statuses=("DONE",))

    with mock_munge_auth(app, uid=0):
        response = await client.get(
            accounting_endpoint + f"?ended_after=2020-01-01T00:00:00&{query}"
        )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == N_USERS
    assert response.json()["pagination"]["start"] == expected_start
    assert response.json()["pagination"]["end"] == expected_end
    assert len(response.json()["data"]) == expected_len
    if expected_first_index is not None:
        assert response.json()["data"][0]["user_id"] == user_uids[expected_first_index]


@pytest.mark.asyncio
@pytest.mark.parametrize("n_users,user_index", ((4, [3]), (4, [0, 1, 2, 3]), (4, [])))
async def test_acct_user_id_filtering(
    client, app, accounting_endpoint: str, n_users: int, user_index: list[int]
):
    """Test that accounting routes correctly filter by user_ids"""

    assert n_users < AcctRequest.model_fields["limit"].default

    # One session/job per user to have the test work on all routes
    user_ids, _, _ = await acct_populate_db(
        app,
        n_users=n_users,
    )

    # Build query
    requested_users = [user_ids[i] for i in user_index]
    query = accounting_endpoint
    if requested_users:
        query += "?" + "&".join(list(map(lambda x: f"user_id={x}", requested_users)))
    else:
        # If request user_index is None, request a non-existent user_id
        query += "?user_id=123456789"

    with mock_munge_auth(app, uid=0):
        response = await client.get(query)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == len(user_index)
    for row in data:
        assert row["user_id"] in requested_users


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_users,nth_user_split", ((10, 1), (10, 5), (10, 2), (10, 10))
)
async def test_acct_start_end_filter(
    client, app, accounting_endpoint: str, n_users: int, nth_user_split: int
):
    """Assert that the accounting data query correctly filters sessions/jobs according to start/end datetime."""

    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)

    SESSION_DURATION = timedelta(minutes=45)
    JOB_DURATION = timedelta(minutes=30)
    USER_TIME_OFFSET = timedelta(hours=1)

    # One session/job per user to have the test work on all routes
    user_ids, jobs, sessions = await acct_populate_db(
        app,
        first_session_start=FIRST_SESSION_START,
        n_users=n_users,
        session_duration=SESSION_DURATION,
        user_time_offset=USER_TIME_OFFSET,
        job_execution_time=JOB_DURATION,
        job_statuses=("DONE",),
    )

    # Test time filtering is total partition of data
    # We split the filtering exactly at the end time of
    # the nth_user_split user's session/job

    # If filtering by jobs, split a job endtime
    if accounting_endpoint == ACCT_JOBS_ENDPOINT:
        record_split = jobs[nth_user_split - 1]
        assert record_split.effective_end is not None
        record_split_end = record_split.effective_end
    # If filtering by sesssions, split a session revoked_at
    else:
        record_split = sessions[nth_user_split - 1]
        assert record_split.revoked_at is not None
        record_split_end = record_split.revoked_at

    with mock_munge_auth(app, uid=0):
        response_before = await client.get(
            accounting_endpoint
            + "?ended_before="
            + record_split_end.isoformat()
            + "&limit=100"
        )
        response_after = await client.get(
            accounting_endpoint
            + "?ended_after="
            + record_split_end.isoformat()
            + "&limit=100"
        )
    assert response_before.status_code == 200
    assert response_after.status_code == 200

    if nth_user_split > 1:
        assert response_before.json()["data"][0]["user_id"] == user_ids[0]
    if nth_user_split < n_users:
        assert (
            response_after.json()["data"][0]["user_id"] == user_ids[nth_user_split - 1]
        )

    count_before = len(response_before.json()["data"])
    count_after = len(response_after.json()["data"])
    assert count_before == (nth_user_split - 1)
    assert count_after == n_users - (nth_user_split - 1)
    assert count_before + count_after == n_users


@pytest.mark.asyncio
async def test_acct_excludes_not_yet_ended(client, app, accounting_endpoint: str):
    """Assert that sessions/jobs which are not over yet are excluded from the
    accounting calculation, even without any start/end filter applied: a
    session with no `revoked_at`, or a job with no `effective_end`, has no
    defined duration and must never be reported."""

    N_ENDED_USERS = 3

    # N_ENDED_USERS fully-ended users, one session/job each.
    user_uids, _, sessions = await acct_populate_db(app, n_users=N_ENDED_USERS)

    # An extra user whose session is still active (not revoked).
    active_session = Session(
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        revoked_at=None,
        user_id="9999",
        slurm_job_id="active-session",
    )
    # A still-running job attached to the first ended user's session.
    active_job = Job(
        status="RUNNING",
        logs="",
        shots=100,
        sequence="",
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        scheduled_at=datetime(2026, 1, 1, 0, 0, 5),
        started_at=datetime(2026, 1, 1, 0, 0, 5),
        ended_at=None,
        session=sessions[0],
    )

    async_session_factory = app.state.db_session_factory
    async with async_session_factory() as db_session:
        db_session.add_all([active_session, active_job])
        await db_session.commit()

    with mock_munge_auth(app, uid=0):
        response = await client.get(accounting_endpoint + "?limit=100")
    assert response.status_code == 200

    body = response.json()
    assert body["pagination"]["total"] == N_ENDED_USERS
    data = body["data"]
    assert len(data) == N_ENDED_USERS
    # The not-yet-ended session's user never shows up, regardless of route.
    assert all(row["user_id"] != "9999" for row in data)

    if accounting_endpoint == ACCT_JOBS_ENDPOINT:
        # The still-running job on the first user's session is excluded,
        # only the already-DONE job remains.
        assert all(row["status"] != "RUNNING" for row in data)
    elif accounting_endpoint == ACCT_ENDPOINT:
        # /accounting: the first user's job summary must not count the
        # still-running job.
        first_user_data = next(row for row in data if row["user_id"] == user_uids[0])
        assert first_user_data["jobs"]["count"] == 1


@pytest.mark.asyncio
async def test_acct_start_end_filter_accepts_timezone_aware_query_params(
    client, app, accounting_endpoint: str
):
    """Assert that a ended_after with a non-UTC offset selects the same
    rows as its naive-UTC equivalent, i.e. the request-level normalization
    is actually applied to query params, not just direct model usage."""

    N_USERS = 10
    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)
    SESSION_DURATION = timedelta(minutes=45)
    USER_TIME_OFFSET = timedelta(hours=1)

    # One session/job per user to have the test work on all routes
    _, jobs, sessions = await acct_populate_db(
        app,
        first_session_start=FIRST_SESSION_START,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        user_time_offset=USER_TIME_OFFSET,
    )
    # If filtering by jobs, split a job endtime
    if accounting_endpoint == ACCT_JOBS_ENDPOINT:
        record = jobs[1]
        assert record.effective_end is not None
        record_end = record.effective_end
    # If filtering by sesssions, split a session revoked_at
    else:
        record = sessions[1]
        assert record.revoked_at is not None
        record_end = record.revoked_at

    # Same instant as `revoked_at` (naive, assumed UTC), expressed at UTC+2.
    aware_equivalent = (record_end + timedelta(hours=2)).replace(
        tzinfo=timezone(timedelta(hours=2))
    )

    with mock_munge_auth(app, uid=0):
        response_naive = await client.get(
            accounting_endpoint
            + "?ended_after="
            + record_end.isoformat()
            + "&limit=100"
        )
        response_aware = await client.get(
            accounting_endpoint
            + "?ended_after="
            # `+` is form-encoding shorthand for a space in query strings, so
            # a raw `+HH:MM` offset must be percent-encoded, same as any real
            # HTTP client does automatically (e.g. httpx's `params=` kwarg).
            + quote(aware_equivalent.isoformat())
            + "&limit=100"
        )
    assert response_naive.status_code == 200
    assert response_aware.status_code == 200
    assert len(response_aware.json()["data"]) == 9
    assert len(response_naive.json()["data"]) == 9
    assert response_naive.json()["data"] == response_aware.json()["data"]

@pytest.mark.asyncio
@pytest.mark.parametrize("n_sessions, session_index", ((10, [5]), (10, []), (4, [0, 1, 2, 3])))
async def test_acct_records_session_id_filtering(client, app, accounting_records_endpoint, n_sessions: int, session_index: list[int]):

    STATUSES = ("DONE", "ERROR", "CANCELED")

    # 1 session per user, 3 jobs per session
    _, _, sessions = await acct_populate_db(app, n_users=n_sessions, job_statuses=STATUSES)

    with mock_munge_auth(app, uid=0):
        response = await client.get(accounting_records_endpoint)

    requested_sessions = [str(sessions[i].id) for i in session_index]
    query = accounting_records_endpoint
    if requested_sessions:
        query += "?" + "&".join(list(map(lambda x: f"session_id={x}", requested_sessions)))
    else:
        # If request session_id is None, request a non-existent user_id
        query += "?session_id=12345678-1234-1234-1234-123456789abc"

    with mock_munge_auth(app, uid=0):
        response = await client.get(query)
    assert response.status_code == 200
    data = response.json()["data"]
    if accounting_records_endpoint == ACCT_JOBS_ENDPOINT:
        assert len(data) == len(session_index) * 3
        for row in data:
            assert row["session_id"] in requested_sessions
    else:
        assert len(data) == len(session_index)
        for row in data:
            assert row["id"] in requested_sessions

@pytest.mark.asyncio
@pytest.mark.parametrize("n_sessions, session_index", ((10, [5]), (10, []), (4, [0, 1, 2, 3])))
async def test_acct_records_slurm_job_id_filtering(client, app, accounting_records_endpoint, n_sessions: int, session_index: list[int]):

    STATUSES = ("DONE", "ERROR", "CANCELED")

    # 1 session per user, 3 jobs per session
    _, _, sessions = await acct_populate_db(app, n_users=n_sessions, job_statuses=STATUSES)

    with mock_munge_auth(app, uid=0):
        response = await client.get(accounting_records_endpoint)

    requested_slurm_job_id = [str(sessions[i].slurm_job_id) for i in session_index]
    query = accounting_records_endpoint
    if requested_slurm_job_id:
        query += "?" + "&".join(list(map(lambda x: f"slurm_job_id={x}", requested_slurm_job_id)))
    else:
        # If request session_id is None, request a non-existent user_id
        query += "?slurm_job_id=00000000000000000000000000000"

    with mock_munge_auth(app, uid=0):
        response = await client.get(query)
    assert response.status_code == 200
    data = response.json()["data"]
    if accounting_records_endpoint == ACCT_JOBS_ENDPOINT:
        assert len(data) == len(session_index) * 3
    else:
        assert len(data) == len(session_index)

    for row in data:
        assert row["slurm_job_id"] in requested_slurm_job_id
