"""Testing lib/qpu_client/retry"""

import pytest

from warden.lib.qpu_client.auth import TokenRequestError
from warden.lib.qpu_client.retry import UnhandledError, retry


@pytest.mark.asyncio
async def test_already_classified_errors_are_not_rewrapped():
    calls = {"n": 0}

    @retry(max=5, sleep_s=0)
    async def fails_with_bad_credentials():
        calls["n"] += 1
        raise TokenRequestError("invalid_client")

    with pytest.raises(TokenRequestError):
        await fails_with_bad_credentials()

    # Fail fast: a wrong secret will not fix itself.
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_unknown_errors_are_still_wrapped():
    @retry(max=5, sleep_s=0)
    async def fails_with_value_error():
        raise ValueError("something unexpected")

    with pytest.raises(UnhandledError):
        await fails_with_value_error()
