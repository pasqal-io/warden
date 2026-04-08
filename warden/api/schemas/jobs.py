from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from warden.lib.models.jobs import Job


class JobCreate(BaseModel):
    sequence: str | AHSSequence
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
