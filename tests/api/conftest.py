import json
from contextlib import contextmanager
from typing import Callable, Generator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response

from warden.api.app import create_app
from warden.api.routes.dependencies.auth import MungeIdentity, munge_identity
from warden.api.routes.dependencies.qpu_client import get_qpu_client
from warden.lib.config.config import APIConfig, Config, QPUConfig, SqliteConfig
from warden.lib.db.database import Base
from warden.lib.qpu_client.client import AsyncQPUClient


@pytest.fixture
def config():
    db_config = SqliteConfig(name="warden_tests.db", backend="sqlite", echo=False)
    api = APIConfig(host="0.0.0.0", port=9999, authorized_users=[])
    yield Config(database=db_config, api=api)


@pytest_asyncio.fixture
async def app(config):
    app: FastAPI = create_app(config)
    async with app.state.db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield app
    async with app.state.db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    # create tables in the test database
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


MAX_RETRY = 10


def make_qpu_client(handler: Callable[[Request], Response]) -> AsyncQPUClient:
    """Create a QPUClient with a mocked HTTP transport."""
    config = QPUConfig(uri="http://mock-qpu", retry_max=MAX_RETRY, retry_sleep_s=0)
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
    app, uid: int = 0, payload: bytes = b""
) -> Generator[None, None, None]:
    # The mock now uses the arguments passed to the context manager
    async def munge_identity_mock() -> MungeIdentity:
        return MungeIdentity(uid=uid, payload=payload)

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
