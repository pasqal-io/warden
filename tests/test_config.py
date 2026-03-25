"""Testing lib/config"""

import pytest

from pydantic import ValidationError

from warden.lib.config.config import SchedulerConfig


def test_scheduler_config():
    with pytest.raises(ValidationError):
        SchedulerConfig(strategy="NOT_FIFO", db_polling_interval_s=1)
