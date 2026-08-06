from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote

import pytest

from tests.api.acct.conftest import acct_populate_db
from tests.api.conftest import mock_munge_auth
from warden.api.schemas.acct import AcctRequest

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
async def test_acct_user_id_filtering(client, app, accounting_endpoint: str):
    """Test that accounting routes correctly filter by user_ids

    Rationale:
    - Populate DB with 10 users with each one session with one job
    - So, for any route, len(data) = number of user_id selected
    """

    N_USERS = 10

    user_ids, _, _ = await acct_populate_db(
        app,
        N_USERS,
    )

    # No filter
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            accounting_endpoint + "?ended_after=1999-01-01&limit=10"
        )
    assert response.status_code == 200
    assert len(response.json()["data"]) == N_USERS

    # Filter with all user_ids
    with mock_munge_auth(app, uid=0):
        request = accounting_endpoint + "?ended_after=1999-01-01&limit=10"
        for user_id in user_ids:
            request += "&user_ids=" + user_id
        response = await client.get(request)
    assert response.status_code == 200
    assert len(response.json()["data"]) == N_USERS

    # Filter with 3 existing user_ids
    selected_ids = user_ids[:3]
    with mock_munge_auth(app, uid=0):
        request = accounting_endpoint + "?ended_after=1999-01-01&limit=10"
        for user_id in selected_ids:
            request += "&user_ids=" + user_id
        response = await client.get(request)
    assert response.status_code == 200
    assert len(response.json()["data"]) == 3
    for row in response.json()["data"]:
        assert row["user_id"] in selected_ids

    # Filter with a non-existent user_id
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            accounting_endpoint
            + "?ended_after=1999-01-01&limit=10"
            + "&user_ids=9999999999999999999999999"
        )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 0


@pytest.mark.asyncio
async def test_acct_datetime_filter(client, app, accounting_endpoint: str):
    """Assert that the accounting data query correctly filters sessions according to start/end datetime."""

    N_USERS = 10
    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)

    SESSION_DURATION = timedelta(minutes=45)
    USER_TIME_OFFSET = timedelta(hours=1)

    user_ids, _, sessions = await acct_populate_db(
        app,
        first_session_start=FIRST_SESSION_START,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        user_time_offset=USER_TIME_OFFSET,
        job_statuses=("DONE",),
    )

    # Test default get all
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            accounting_endpoint + "?ended_after=" + FIRST_SESSION_START.isoformat()
        )
    assert response.status_code == 200
    assert len(response.json()["data"]) == N_USERS
    assert response.json()["data"][0]["user_id"] == user_ids[0]

    # Test filtering only first user session
    first_session = sessions[0]
    assert first_session.revoked_at is not None
    with mock_munge_auth(app, uid=0):
        response = await client.get(
            accounting_endpoint
            + "?ended_after="
            + FIRST_SESSION_START.isoformat()
            + "&ended_before="
            + (first_session.revoked_at + timedelta(seconds=1)).isoformat()
        )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["user_id"] == user_ids[0]

    # Test time filtering is total partition of data
    # We split the filtering exactly at the revocation time of the 2nd user's session
    second_session = sessions[1]
    assert second_session.revoked_at is not None
    with mock_munge_auth(app, uid=0):
        response_before = await client.get(
            accounting_endpoint
            + "?ended_after="
            + FIRST_SESSION_START.isoformat()
            + "&ended_before="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
        response_after = await client.get(
            accounting_endpoint
            + "?ended_after="
            + second_session.revoked_at.isoformat()
            + "&limit=100"
        )
    assert response_after.status_code == 200
    assert response_before.status_code == 200

    assert len(response_before.json()["data"]) == 1
    assert len(response_after.json()["data"]) == 9


@pytest.mark.asyncio
async def test_acct_datetime_filter_accepts_timezone_aware_query_params(
    client, app, accounting_endpoint: str
):
    """Assert that a ended_after with a non-UTC offset selects the same
    rows as its naive-UTC equivalent, i.e. the request-level normalization
    is actually applied to query params, not just direct model usage."""

    N_USERS = 10
    FIRST_SESSION_START = datetime(2026, 1, 1, 0, 0, 0)
    SESSION_DURATION = timedelta(minutes=45)
    USER_TIME_OFFSET = timedelta(hours=1)

    _, _, sessions = await acct_populate_db(
        app,
        first_session_start=FIRST_SESSION_START,
        n_users=N_USERS,
        session_duration=SESSION_DURATION,
        user_time_offset=USER_TIME_OFFSET,
    )

    second_session = sessions[1]
    assert second_session.revoked_at is not None

    # Same instant as `revoked_at` (naive, assumed UTC), expressed at UTC+2.
    aware_equivalent = (second_session.revoked_at + timedelta(hours=2)).replace(
        tzinfo=timezone(timedelta(hours=2))
    )

    with mock_munge_auth(app, uid=0):
        response_naive = await client.get(
            accounting_endpoint
            + "?ended_after="
            + second_session.revoked_at.isoformat()
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
    assert response_naive.json()["data"] == response_aware.json()["data"]
