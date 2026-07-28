"""Testing lib/qpu_client/types — UTCDatetime Pydantic validator"""

from datetime import datetime, timedelta, timezone

from warden.lib.qpu_client.types import QPUJobInfo


def _api_data(**overrides) -> dict:
    """Return a minimal valid QPUJobInfo payload."""
    data = dict(
        uid=1,
        batch_id=None,
        status=None,
        result=None,
        program_id=None,
        created_datetime=datetime(2024, 1, 15, 12, 0, 0),
        start_datetime=None,
        end_datetime=None,
    )
    data.update(overrides)
    return data


def test_naive_datetime_is_coerced_to_utc():
    """A naive created_datetime is assumed UTC and given UTC tzinfo."""
    naive = datetime.now()
    assert naive.tzinfo is None

    job = QPUJobInfo(**_api_data(created_datetime=naive))

    assert job.created_datetime.tzinfo == timezone.utc
    assert job.created_datetime.replace(tzinfo=None) == naive


def test_utc_aware_datetime_is_unchanged():
    """A UTC-aware created_datetime passes through without modification."""
    utc_dt = datetime.now(tz=timezone.utc)

    job = QPUJobInfo(**_api_data(created_datetime=utc_dt))

    assert job.created_datetime == utc_dt
    assert job.created_datetime.tzinfo == timezone.utc


def test_non_utc_aware_datetime_is_converted_to_utc():
    """A non-UTC timezone-aware created_datetime is converted to UTC."""
    minus_five = timezone(timedelta(hours=-5))
    minus_five_dt = datetime(2024, 1, 15, 7, 0, 0, tzinfo=minus_five)
    expected_utc = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    job = QPUJobInfo(**_api_data(created_datetime=minus_five_dt))

    assert job.created_datetime == expected_utc
    assert job.created_datetime.tzinfo == timezone.utc


def test_optional_utc_datetime_field_none_is_accepted():
    """Optional UTCDatetime fields (start/end) accept None without error."""
    job = QPUJobInfo(**_api_data(start_datetime=None, end_datetime=None))

    assert job.start_datetime is None
    assert job.end_datetime is None


def test_optional_utc_datetime_field_naive_is_coerced():
    """Optional UTCDatetime fields coerce naive datetimes to UTC."""
    naive = datetime.now()

    job = QPUJobInfo(**_api_data(start_datetime=naive, end_datetime=naive))

    assert job.start_datetime is not None
    assert job.start_datetime.tzinfo == timezone.utc
    assert job.end_datetime is not None
    assert job.end_datetime.tzinfo == timezone.utc
    assert job.start_datetime.replace(tzinfo=None) == naive


def test_optional_utc_datetime_field_non_utc_is_converted():
    """Optional UTCDatetime fields convert non-UTC aware datetimes to UTC."""
    plus_two = timezone(timedelta(hours=2))
    local_dt = datetime(2024, 6, 1, 10, 0, 0, tzinfo=plus_two)
    expected_utc = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)

    job = QPUJobInfo(**_api_data(end_datetime=local_dt))

    assert job.end_datetime == expected_utc
