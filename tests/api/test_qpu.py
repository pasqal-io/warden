import json
from contextlib import contextmanager
from typing import Callable, Generator

import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from warden.api.routes.dependencies.qpu_client import get_qpu_client
from warden.lib.qpu_client.client import AsyncQPUClient


@pytest.fixture
def qpu_specs() -> dict:
    return {
        "name": "FRESNEL_CAN1",
        "dimensions": 2,
        "rydberg_level": 60,
        "min_atom_distance": 5,
        "max_atom_num": 100,
        "max_radial_distance": 46,
        "interaction_coeff_xy": None,
        "supports_slm_mask": False,
        "min_layout_filling": 0.35,
        "max_layout_filling": 0.55,
        "optimal_layout_filling": 0.45,
        "min_layout_traps": 60,
        "max_layout_traps": 217,
        "max_sequence_duration": 6000,
        "max_runs": 1000,
        "reusable_channels": False,
        "default_noise_model": {
            "noise_types": ["SPAM", "dephasing", "relaxation"],
            "runs": None,
            "samples_per_run": None,
            "state_prep_error": 0,
            "p_False_pos": 0.025,
            "p_False_neg": 0.1,
            "temperature": 0,
            "laser_waist": None,
            "amp_sigma": 0,
            "relaxation_rate": 0.01,
            "dephasing_rate": 0.2222222222222222,
            "hyperfine_dephasing_rate": 0,
            "depolarizing_rate": 0,
            "eff_noise": [],
        },
        "pre_calibrated_layouts": [],
        "version": "1",
        "pulser_version": "1.5.4",
        "channels": [
            {
                "id": "rydberg_global",
                "basis": "ground-rydberg",
                "addressing": "Global",
                "max_abs_detuning": 62.83185307179586,
                "max_amp": 12.566370614359172,
                "min_retarget_interval": None,
                "fixed_retarget_t": None,
                "max_targets": None,
                "clock_period": 4,
                "min_duration": 16,
                "max_duration": 6000,
                "min_avg_amp": 0.3141592653589793,
                "mod_bandwidth": 5,
                "custom_phase_jump_time": 0,
                "eom_config": {
                    "limiting_beam": "RED",
                    "max_limiting_amp": 175.92918860102841,
                    "intermediate_detuning": 2827.4333882308138,
                    "controlled_beams": ["BLUE"],
                    "mod_bandwidth": 26,
                    "custom_buffer_time": 240,
                    "multiple_beam_control": False,
                    "red_shift_coeff": 2,
                },
                "propagation_dir": [0, 1, 0],
            }
        ],
        "is_virtual": False,
    }


def make_qpu_client(handler: Callable[[Request], Response]) -> AsyncQPUClient:
    """Create a QPUClient with a mocked HTTP transport."""
    client = AsyncQPUClient(uri="http://mock-qpu")
    client.client = AsyncClient(transport=MockTransport(handler))
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


@pytest.mark.asyncio
async def test_get_specs_success(client: AsyncClient, app, qpu_specs: dict):
    """Nominal test case: assert that QPU specs are returned successfully.

    1. Mock the QPU HTTP response to return a known specs payload
    2. Call GET /qpu/specs
    3. Assert the response matches the mocked specs
    """

    def handler(request: Request) -> Response:
        return Response(200, json={"data": {"specs": qpu_specs}})

    with mock_qpu_client(app, handler):
        response = await client.get("/qpu/specs")

    assert response.status_code == 200
    data = response.json()
    assert data["specs"] == json.dumps(qpu_specs)


@pytest.mark.asyncio
async def test_get_specs_qpu_unavailable(client: AsyncClient, app):
    """Assert that a QPU error response is propagated correctly.

    1. Mock the QPU HTTP response to return a 503
    2. Call GET /qpu/specs
    3. Assert the response returns a 500 error
    """

    def handler(request: Request) -> Response:
        return Response(503, json={"error": "QPU unavailable"})

    with mock_qpu_client(app, handler):
        response = await client.get("/qpu/specs")

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_specs_connection_refused(client: AsyncClient, app):
    """Assert that connection refused errors are handled gracefully.

    1. Mock the QPU HTTP transport to raise a connection error
    2. Call GET /qpu/specs
    3. Assert the response returns a 500 error
    """

    def handler(request: Request) -> Response:
        raise ConnectionError("Connection refused")

    with mock_qpu_client(app, handler):
        response = await client.get("/qpu/specs")

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_specs_host_unreachable(client: AsyncClient, app):
    """Assert that host unreachable errors are handled gracefully.

    1. Mock the QPU HTTP transport to raise a connection error (host unreachable)
    2. Call GET /qpu/specs
    3. Assert the response returns a 500 error
    """

    def handler(request: Request) -> Response:
        raise OSError("No route to host")

    with mock_qpu_client(app, handler):
        response = await client.get("/qpu/specs")

    assert response.status_code == 500
