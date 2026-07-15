import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import AsyncGenerator, Callable, Generator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
from pulser.devices import DigitalAnalogDevice

from warden.api.app import create_app
from warden.api.routes.dependencies.auth import MungeIdentity, munge_identity
from warden.api.routes.dependencies.qpu_client import get_qpu_client
from warden.lib.config.config import APIConfig, Config, DatabaseConfig, QPUConfig
from warden.lib.db.database import Base
from warden.lib.models import Job, Session
from warden.lib.qpu_client.client import AsyncQPUClient


@pytest_asyncio.fixture
async def app(db_backend_config: DatabaseConfig) -> AsyncGenerator[FastAPI, None]:
    api = APIConfig(port=9999)
    config = Config(database=db_backend_config, api=api)
    app: FastAPI = create_app(config)
    # create tables in the test database
    async with app.state.db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield app
    async with app.state.db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


MAX_RETRY = 10


def make_qpu_client(handler: Callable[[Request], Response]) -> AsyncQPUClient:
    """Create a QPUClient with a mocked HTTP transport."""
    config = QPUConfig(uri="http://mock-qpu", retry_sleep_s=0)
    client = AsyncQPUClient(config)
    client.client = AsyncClient(
        base_url=config.uri + "/api/v1", transport=MockTransport(handler)
    )
    return client


@contextmanager
def mock_qpu_client(
    app, handler: Callable[[Request], Response]
) -> Generator[None, None, None]:
    app.dependency_overrides[get_qpu_client] = lambda: make_qpu_client(handler)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_qpu_client, None)


@contextmanager
def mock_munge_auth(
    app: FastAPI, uid: int = 0, payload: bytes = b""
) -> Generator[None, None, None]:
    # The mock now uses the arguments passed to the context manager
    async def munge_identity_mock() -> MungeIdentity:
        return MungeIdentity(uid=str(uid), payload=payload)

    app.dependency_overrides[munge_identity] = munge_identity_mock

    try:
        yield
    finally:
        app.dependency_overrides.pop(munge_identity, None)


@pytest.fixture
def serialized_sequence() -> str:
    return json.dumps(
        {
            "version": "1",
            "name": "pulser-exported",
            "register": [
                {"name": "q0", "x": -2.5, "y": -2.5},
                {"name": "q1", "x": 2.5, "y": -2.5},
                {"name": "q2", "x": -2.5, "y": 2.5},
                {"name": "q3", "x": 2.5, "y": 2.5},
            ],
            "channels": {"rydberg": "rydberg_global"},
            "variables": {"omega_max": {"type": "float", "value": [0.0]}},
            "operations": [
                {
                    "op": "pulse",
                    "channel": "rydberg",
                    "protocol": "min-delay",
                    "post_phase_shift": 0.0,
                    "amplitude": {
                        "kind": "constant",
                        "duration": 100,
                        "value": {
                            "expression": "index",
                            "lhs": {"variable": "omega_max"},
                            "rhs": 0,
                        },
                    },
                    "detuning": {"kind": "constant", "duration": 100, "value": 2.0},
                    "phase": 0.0,
                }
            ],
            "measurement": None,
            "pulser_version": "1.7.0",
            "device": {
                "name": "DigitalAnalogDevice",
                "dimensions": 2,
                "rydberg_level": 70,
                "min_atom_distance": 4,
                "max_atom_num": 100,
                "max_radial_distance": 50,
                "interaction_coeff_xy": None,
                "supports_slm_mask": True,
                "max_layout_filling": 0.5,
                "reusable_channels": False,
                "pre_calibrated_layouts": [],
                "version": "1",
                "pulser_version": "1.7.0",
                "channels": [
                    {
                        "id": "rydberg_global",
                        "basis": "ground-rydberg",
                        "addressing": "Global",
                        "max_abs_detuning": 125.66370614359172,
                        "max_amp": 15.707963267948966,
                        "min_retarget_interval": None,
                        "fixed_retarget_t": None,
                        "max_targets": None,
                        "clock_period": 4,
                        "min_duration": 16,
                        "max_duration": 67108864,
                        "mod_bandwidth": None,
                        "eom_config": None,
                    },
                    {
                        "id": "rydberg_local",
                        "basis": "ground-rydberg",
                        "addressing": "Local",
                        "max_abs_detuning": 125.66370614359172,
                        "max_amp": 62.83185307179586,
                        "min_retarget_interval": 220,
                        "fixed_retarget_t": 0,
                        "max_targets": 1,
                        "clock_period": 4,
                        "min_duration": 16,
                        "max_duration": 67108864,
                        "mod_bandwidth": None,
                        "eom_config": None,
                    },
                    {
                        "id": "raman_local",
                        "basis": "digital",
                        "addressing": "Local",
                        "max_abs_detuning": 125.66370614359172,
                        "max_amp": 62.83185307179586,
                        "min_retarget_interval": 220,
                        "fixed_retarget_t": 0,
                        "max_targets": 1,
                        "clock_period": 4,
                        "min_duration": 16,
                        "max_duration": 67108864,
                        "mod_bandwidth": None,
                        "eom_config": None,
                    },
                ],
                "dmm_objects": [
                    {
                        "id": "dmm_0",
                        "basis": "ground-rydberg",
                        "addressing": "Global",
                        "max_abs_detuning": None,
                        "max_amp": 0,
                        "min_retarget_interval": None,
                        "fixed_retarget_t": None,
                        "max_targets": None,
                        "clock_period": 4,
                        "min_duration": 16,
                        "max_duration": 67108864,
                        "mod_bandwidth": None,
                        "eom_config": None,
                        "bottom_detuning": -125.66370614359172,
                        "total_bottom_detuning": -12566.370614359172,
                    }
                ],
                "is_virtual": False,
            },
        }
    )


@pytest.fixture
def cudaq_sequence() -> str:
    return json.dumps(
        {
            "setup": {
                "ahs_register": {
                    "sites": [[0.0, 0.0], [5e-6, 0.0], [0.0, 5e-6], [5e-6, 5e-6]],
                    "filling": [1, 1, 1, 1],
                }
            },
            "hamiltonian": {
                "drivingFields": [
                    {
                        "amplitude": {
                            "pattern": "uniform",
                            "time_series": {
                                "values": [0.0, 1e6],
                                "times": [0.0, 1e-7],
                            },
                        },
                        "phase": {
                            "pattern": "uniform",
                            "time_series": {
                                "values": [0.0, 0.0],
                                "times": [0.0, 1e-7],
                            },
                        },
                        "detuning": {
                            "pattern": "uniform",
                            "time_series": {
                                "values": [0.0, 0.0],
                                "times": [0.0, 1e-7],
                            },
                        },
                    }
                ],
                "localDetuning": [],
            },
        }
    )


@pytest.fixture
def cudaq_payload(cudaq_sequence: str) -> dict:
    return {"shots": 100, "sequence": cudaq_sequence}


@pytest.fixture
def qpu_specs() -> dict:
    specs = json.loads(DigitalAnalogDevice.to_abstract_repr())
    specs["name"] = "FRESNEL_CAN1"
    return specs


async def acct_populate_db(
    app,
    serialized_sequence: str,
    n_users: int,
    first_session_start: datetime = datetime(2026, 1, 1, 0, 0, 0),
    session_duration: timedelta = timedelta(hours=1),
    user_time_offset: timedelta = timedelta(hours=1),
) -> tuple[list[str], list[Job], list[Session]]:
    """Creates mock data for accounting testing in DB"""
    BASE_START_DATETIME = first_session_start
    BASE_END_DATETIME = BASE_START_DATETIME + session_duration
    user_uids = [str(i) for i in range(1000, 1000 + n_users)]

    # Create at least one session and job per user
    sessions = []
    jobs = []
    for i, uid in enumerate(user_uids):
        start_session = BASE_START_DATETIME + i * user_time_offset
        end_session = BASE_END_DATETIME + i * user_time_offset

        sessions.append(
            Session(
                created_at=start_session,
                revoked_at=end_session,
                user_id=uid,
                slurm_job_id=str(i),
            )
        )
        jobs.append(
            Job(
                status="DONE",
                logs="",
                shots=100,
                sequence=serialized_sequence,
                created_at=start_session,
                scheduled_at=start_session,
                started_at=start_session,
                ended_at=end_session,
                # Relationship
                session=sessions[-1],
            )
        )

    async_session_factory = app.state.db_session_factory
    async with async_session_factory() as db_session:
        db_session.add_all(sessions)
        db_session.add_all(jobs)
        await db_session.commit()
    return user_uids, jobs, sessions
