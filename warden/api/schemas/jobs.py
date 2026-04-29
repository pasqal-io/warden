from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, BeforeValidator, TypeAdapter, ValidationError

from warden.lib.models.jobs import Job


def _try_parse_AHSSequence(sequence: Any):
    """Try parsing input sequence as a CudaQ payload"""
    if not isinstance(sequence, str):
        return sequence
    try:
        data = json.loads(sequence)
        TypeAdapter(AHSSequence).validate_python(data)
        return data
    except (ValidationError, ValueError, json.JSONDecodeError):
        return sequence


class JobCreate(BaseModel):
    sequence: Annotated[
        Union[AHSSequence, str], BeforeValidator(_try_parse_AHSSequence)
    ]
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
