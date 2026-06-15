from typing import Annotated

from fastapi import Depends, FastAPI, Request


def init_admin_users(app: FastAPI, admin_users: list[str]):
    app.state.admin_users = admin_users


def get_admin_users(request: Request) -> list[str]:
    conf = getattr(request.app.state, "admin_users", None)
    if conf is None:
        raise RuntimeError(
            "Config not initialized. init_admin_users(app, ...) was not called."
        )
    return conf


AdminUsersDep = Annotated[list[str], Depends(get_admin_users)]
