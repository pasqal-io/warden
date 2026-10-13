from typing import Annotated

from fastapi import Depends, FastAPI, Request

from warden.lib.config import SessionConfig


def init_session_config(app: FastAPI, session_config: SessionConfig) -> None:
    """Store session lifecycle configuration on the application."""
    app.state.session_config = session_config


def get_session_config(request: Request) -> SessionConfig:
    """Return session lifecycle configuration."""
    return request.app.state.session_config


SessionConfigDep = Annotated[SessionConfig, Depends(get_session_config)]
