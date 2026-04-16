from typing import Annotated

from fastapi import Depends, FastAPI, Request

from warden.lib.config import APIConfig


def init_authorized_users(app: FastAPI, api_config: APIConfig):
    app.state.authorized_users = api_config.authorized_users


def get_authorized_users(request: Request) -> APIConfig:
    conf = getattr(request.app.state, "authorized_users", None)
    if conf is None:
        raise RuntimeError(
            "Config not initialized. init_authorized_users(app, ...) was not called."
        )
    return conf


AuthorizedUsersDep = Annotated[APIConfig, Depends(get_authorized_users)]
