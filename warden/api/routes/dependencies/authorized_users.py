from typing import Annotated

from fastapi import Depends, FastAPI, Request


def init_authorized_users(app: FastAPI, authorized_users: list[str]):
    app.state.authorized_users = authorized_users


def get_authorized_users(request: Request) -> list[str]:
    conf = getattr(request.app.state, "authorized_users", None)
    if conf is None:
        raise RuntimeError(
            "Config not initialized. init_authorized_users(app, ...) was not called."
        )
    return conf


AuthorizedUsersDep = Annotated[list[str], Depends(get_authorized_users)]
