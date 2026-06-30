"""Dependecy for timed mocking job execution duration"""

import os
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from mock_qpu_api.config import TimedConfig
from mock_qpu_api.models.jobs import DEFAULT_SHOT_DURATION_S


def init_timed_job(app: FastAPI) -> None:
    is_timed = "MOCK_QPU_API_IS_TIMED" in os.environ
    shot_duration_s = float(
        os.environ.get("MOCK_QPU_API_SHOT_DURATION_S", DEFAULT_SHOT_DURATION_S)
    )
    app.state.timed_config = TimedConfig(
        is_timed=is_timed,
        shot_duration_s=shot_duration_s,
    )


def get_timed_config(request: Request) -> TimedConfig:
    """Get the API configuration for timed job execution."""
    return request.app.state.timed_config


TimedConfigDep = Annotated[TimedConfig, Depends(get_timed_config)]
