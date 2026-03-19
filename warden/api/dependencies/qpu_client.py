from fastapi import FastAPI, Request
from warden.config.config import QPUConfig
from warden.qpu_client import QPUClient


def init_qpu_client(app: FastAPI, qpu_config: QPUConfig):
    """Initialize the QPU client."""
    app.state.qpu_client = QPUClient(qpu_config.url)


def get_qpu_client(request: Request) -> QPUClient:
    """Get the initialized http client to interact with the QPU."""
    return request.app.state.qpu_client
