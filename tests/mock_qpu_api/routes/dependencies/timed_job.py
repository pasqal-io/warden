"""Dependecy for timed mocking job execution duration"""

import os
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from mock_qpu_api.models.jobs import DEFAULT_SHOT_DURATION_S


def init_timed_job(app: FastAPI) -> None:
    app.state.is_timed = "MOCK_QPU_API_IS_TIMED" in os.environ
    app.state.shot_duration_s = float(
        os.environ.get("MOCK_QPU_API_SHOT_DURATION_S", DEFAULT_SHOT_DURATION_S)
    )


def get_is_timed(request: Request) -> bool:
    """Check wether the API is setup to run jobs in timed mode."""
    return request.app.state.is_timed


def get_shot_duration(request: Request) -> float:
    """Get the configured duration of each shot in seconds."""
    return request.app.state.shot_duration_s


IsTimedDep = Annotated[bool, Depends(get_is_timed)]
ShotDurationDep = Annotated[float, Depends(get_shot_duration)]
