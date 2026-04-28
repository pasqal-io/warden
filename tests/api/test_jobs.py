import json

import pytest
from conftest import mock_munge_auth, mock_qpu_client
from httpx import AsyncClient, Request, Response

from warden.lib.models.jobs import Job
from warden.lib.models.sessions import Session


@pytest.fixture
def cudaq_payload() -> str:
    return json.dumps(
        {
            "shots": 100,
            "sequence": {
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
            },
        }
    )


@pytest.mark.asyncio
async def test_job_nominal_flow_success(
    client: AsyncClient, app, serialized_sequence: str
):
    """Test the nominal flow for the slurm spank plugin:

    1. Create a session using root munge token for a given user
    2. With that user create a job
    3. Get the list of jobs as that user.
    4. Revoke the session
    5. Send a new job, it should be rejected

    """
    # 1. Create the session as the root user for the final user
    user_id = 1000
    with mock_munge_auth(app, uid=0):
        response = await client.post(
            "/sessions",
            json={"user_id": str(user_id), "slurm_job_id": "1"},
        )
    assert response.status_code == 200
    session_id = response.json()["id"]

    # 2. Create a job as the final user
    payload = {"sequence": serialized_sequence, "shots": 100}
    with mock_munge_auth(app, uid=user_id):
        response = await client.post(
            "/jobs", json=payload, headers={"X-Warden-Session": session_id}
        )
    assert response.status_code == 200
    job_id = response.json()["id"]

    # 3. Get the job
    with mock_munge_auth(app, uid=user_id):
        response = await client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_id)

    # 4. Revoke the session as the root user
    with mock_munge_auth(app, uid=0):
        response = await client.delete(f"/sessions/{session_id}")
    assert response.status_code == 200

    # 5. Send a job on the revoked session
    # This should return a 403 error
    with mock_munge_auth(app, uid=user_id):
        response = await client.post(
            "/jobs", json=payload, headers={"X-Warden-Session": session_id}
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_job_without_session_header(client, app, serialized_sequence: str):
    """Assert that 403 error is returned when session header is missing
    when receiving a create job request.
    """
    user_id = 1000
    payload = {"sequence": serialized_sequence, "shots": 100}
    with mock_munge_auth(app, uid=user_id):
        response = await client.post("/jobs", json=payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_jobs(client, app, serialized_sequence: str):
    """Assert that only the owned jobs are returned

    1. Create some jobs in db for different users
    2. Call GET /jobs endpoint
    3. Assert only the users owned jobs are returned
    """
    user_id = 1000
    # 1. Create 10 jobs for our user and jobs for other users
    jobs = [
        Job(
            sequence=serialized_sequence,
            shots=100,
            session=Session(slurm_job_id=1, user_id=str(user_id)),
        )
        for _ in range(10)
    ]
    jobs.append(
        Job(
            sequence=serialized_sequence,
            shots=100,
            session=Session(slurm_job_id=2, user_id="1001"),
        )
    )
    jobs.append(
        Job(
            sequence=serialized_sequence,
            shots=100,
            session=Session(slurm_job_id=3, user_id="1002"),
        )
    )
    async_session = app.state.db_session_factory

    async with async_session() as session:
        for job in jobs:
            session.add(job)
        await session.commit()
        await session.refresh(job)

    # 3. Get jobs
    with mock_munge_auth(app, uid=user_id):
        response = await client.get("/jobs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 10
    assert any(job["user_id"] == str(user_id) for job in data)


@pytest.mark.asyncio
async def test_get_job_success(client, app, serialized_sequence: str):
    """Assert that user can a job they own

    1. Create a job in db for a given user
    2. Call GET /job/id endpoint
    3. Assert the job is returned
    """
    user_id = 1000
    job = Job(
        session=Session(user_id=str(user_id), slurm_job_id="1"),
        sequence=serialized_sequence,
        shots=100,
    )
    async_session = app.state.db_session_factory

    async with async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)

    with mock_munge_auth(app, uid=user_id):
        response = await client.get(f"/jobs/{job.id}")
    assert response.status_code == 200
    data = response.json()
    assert job.user_id == data["user_id"]


@pytest.mark.asyncio
async def test_get_job_not_found(client, app, serialized_sequence: str):
    """Assert that API returns 404 error if user tries to access
     a job that doesn't exist in db or if it is owned by another
      user.

    1. Create a job in db for a given user
    2. Call GET /job/id endpoint with a wrong ID
    3. Call GET /job/id with a munge for another user
    Both calls should return 404
    """
    user_id = 1000
    wrong_user_id = 1001
    job = Job(
        session=Session(user_id=str(user_id), slurm_job_id="1"),
        sequence=serialized_sequence,
        shots=100,
    )
    async_session = app.state.db_session_factory

    async with async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)

    wrong_job_id = 120210
    with mock_munge_auth(app, uid=user_id):
        response = await client.get(f"/jobs/{wrong_job_id}")
    assert response.status_code == 404
    with mock_munge_auth(app, uid=wrong_user_id):
        response = await client.get(f"/jobs/{job.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_jobs_auth(client: AsyncClient):
    test_cases = [("POST", "/jobs"), ("GET", "/jobs"), ("GET", "/jobs/1")]
    for method, route in test_cases:
        response = await client.request(method, route)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_job_with_cudaq_payload_nominal(
    client: AsyncClient, app, cudaq_payload: str, qpu_specs: str
):
    """Assert that /jobs accepts CUDA-Q payload and stores normalized Pulser sequence."""
    user_id = 1000

    with mock_munge_auth(app, uid=0):
        response = await client.post(
            "/sessions",
            json={"user_id": str(user_id), "slurm_job_id": "1"},
        )
    assert response.status_code == 200
    session_id = response.json()["id"]

    def handler(request: Request) -> Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/api/v1/system")
        return Response(200, json={"data": {"specs": json.loads(qpu_specs)}})

    with mock_munge_auth(app, uid=user_id), mock_qpu_client(app, handler):
        response = await client.post(
            "/jobs", json=cudaq_payload, headers={"X-Warden-Session": session_id}
        )

    assert response.status_code == 200
    job_id = response.json()["id"]

    async_session = app.state.db_session_factory
    async with async_session() as session:
        job = await session.get(Job, job_id)
    assert job is not None
    assert isinstance(job.sequence, str)
    sequence_dict = json.loads(job.sequence)
    assert "operations" in sequence_dict
    assert sequence_dict["device"]["name"] == "FRESNEL_CAN1"


@pytest.mark.asyncio
async def test_create_job_with_cudaq_payload_specs_fetch_failure_returns_503(
    client: AsyncClient, app, cudaq_payload: str
):
    """Assert that CUDA-Q payload creation returns 503 when fetching QPU specs fails."""
    user_id = 1000

    with mock_munge_auth(app, uid=0):
        response = await client.post(
            "/sessions",
            json={"user_id": str(user_id), "slurm_job_id": "1"},
        )
    assert response.status_code == 200
    session_id = response.json()["id"]

    def handler(request: Request) -> Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/api/v1/system")
        return Response(503, json={"detail": "upstream unavailable"})

    with mock_munge_auth(app, uid=user_id), mock_qpu_client(app, handler):
        response = await client.post(
            "/jobs", json=cudaq_payload, headers={"X-Warden-Session": session_id}
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Failed to fetch QPU specs."


@pytest.mark.asyncio
async def test_create_job_with_cudaq_payload_invalid_sequence_returns_422(
    client: AsyncClient, app, cudaq_payload: str, qpu_specs: str
):
    """Assert that invalid CUDA-Q payload returns 422 from normalization errors."""
    user_id = 1000

    with mock_munge_auth(app, uid=0):
        response = await client.post(
            "/sessions",
            json={"user_id": str(user_id), "slurm_job_id": "1"},
        )
    assert response.status_code == 200
    session_id = response.json()["id"]

    valid_payload = json.loads(cudaq_payload)
    invalid_payload = valid_payload["sequence"]["hamiltonian"]["drivingFields"][0][
        "amplitude"
    ]["pattern"] = "non-uniform"
    invalid_payload = json.dumps(invalid_payload)

    def handler(request: Request) -> Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/api/v1/system")
        return Response(200, json={"data": {"specs": json.loads(qpu_specs)}})

    with mock_munge_auth(app, uid=user_id), mock_qpu_client(app, handler):
        response = await client.post(
            "/jobs", json=invalid_payload, headers={"X-Warden-Session": session_id}
        )

    assert response.status_code == 422
    assert "non-uniform" in response.json()["detail"][0]["input"]
    assert "model_attributes_type" in response.json()["detail"][0]["type"]
