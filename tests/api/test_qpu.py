import json

import pytest
from conftest import MAX_RETRY, mock_qpu_client
from httpx import AsyncClient, Request, Response


@pytest.mark.asyncio
async def test_get_specs_success(client: AsyncClient, app, qpu_specs: str):
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
async def test_get_specs_success_retry(client: AsyncClient, app, qpu_specs: str):
    """Nominal test case: assert that QPU specs are returned successfully
    even after transient PasqOS error retry.

    1. Mock the QPU HTTP response to return a known specs payload after
       several 503 errors
    2. Call GET /qpu/specs
    3. Assert the response matches the mocked specs
    """

    mem = 0

    def handler(request: Request) -> Response:
        nonlocal mem
        if mem == MAX_RETRY - 1:
            return Response(200, json={"data": {"specs": qpu_specs}})
        mem += 1
        return Response(503, json={"error": "QPU unavailable"})

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
    3. Assert the response returns a 503 error
    """

    def handler(request: Request) -> Response:
        return Response(503, json={"error": "QPU unavailable"})

    with mock_qpu_client(app, handler):
        response = await client.get("/qpu/specs")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_specs_connection_refused(client: AsyncClient, app):
    """Assert that connection refused errors are handled gracefully.

    1. Mock the QPU HTTP transport to raise a connection error
    2. Call GET /qpu/specs
    3. Assert the response returns a 503 error
    """

    def handler(request: Request) -> Response:
        raise ConnectionError("Connection refused")

    with mock_qpu_client(app, handler):
        response = await client.get("/qpu/specs")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_specs_host_unreachable(client: AsyncClient, app):
    """Assert that host unreachable errors are handled gracefully.

    1. Mock the QPU HTTP transport to raise a connection error (host unreachable)
    2. Call GET /qpu/specs
    3. Assert the response returns a 503 error
    """

    def handler(request: Request) -> Response:
        raise OSError("No route to host")

    with mock_qpu_client(app, handler):
        response = await client.get("/qpu/specs")

    assert response.status_code == 503
