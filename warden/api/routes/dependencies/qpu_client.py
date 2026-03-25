from fastapi import FastAPI, Request
from warden.lib.config.config import QPUConfig
from warden.lib.qpu_client.client import AsyncQPUClient


def init_qpu_client(app: FastAPI, qpu_config: QPUConfig):
    """Initialize the QPU client."""
    app.state.qpu_client = AsyncQPUClient(qpu_config.uri)


def get_qpu_client(request: Request) -> AsyncQPUClient:
    """Get the initialized http client to interact with the QPU."""
    return request.app.state.qpu_client
