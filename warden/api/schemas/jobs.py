import json
from datetime import datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, Field, ValidationError

from warden.lib.models.jobs import Job


def try_parse_AHSSequence(sequence: str) -> Union[str, "AHSSequence"]:
    """Try parsing input sequence as a CudaQ payload"""
    try:
        data = json.loads(sequence)
        return AHSSequence.model_validate(data)
    except (ValidationError, ValueError, json.JSONDecodeError):
        return sequence


class JobCreate(BaseModel):
    sequence: str
    shots: int


class JobResponse(BaseModel):
    id: int
    user_id: str
    created_at: datetime
    status: str
    results: str | None

    @classmethod
    def from_model(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
            user_id=job.user_id,
            created_at=job.created_at,
            status=job.status,
            results=job.results,
        )


class JobLogResponse(BaseModel):
    logs: str = Field(default="There are no logs for this job")

    @classmethod
    def from_model(cls, job: Job) -> "JobLogResponse":
        if job.logs in (None, ""):
            return cls()
        return cls(
            logs=job.logs,
        )


class AHSTimeSeries(BaseModel):
    values: list[float]
    times: list[float]


class AHSDrivingField(BaseModel):
    pattern: str
    time_series: AHSTimeSeries


class AHSDrivingFields(BaseModel):
    amplitude: AHSDrivingField
    phase: AHSDrivingField
    detuning: AHSDrivingField


class AHSHamiltonian(BaseModel):
    drivingFields: list[AHSDrivingFields]
    localDetuning: list[Any]


class AHSRegister(BaseModel):
    sites: list[list[float]]
    filling: list[Literal[0, 1]]


class AHSSetup(BaseModel):
    ahs_register: AHSRegister


class AHSSequence(BaseModel):
    setup: AHSSetup
    hamiltonian: AHSHamiltonian
