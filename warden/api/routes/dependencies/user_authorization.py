from typing import Annotated

from fastapi import Depends, FastAPI, Request

from warden.api.routes.dependencies.auth import AuthConfig, get_auth_config, init_auth
from warden.lib.config.config import APIConfig


def init_authorization(app: FastAPI, api_config: APIConfig) -> None:
    # Compatibility shim. Prefer init_auth(app, config.api).
    init_auth(app, api_config)


def init_authorized_users(app: FastAPI, authorized_users: list[str]) -> None:
    # Compatibility shim for the old list-only initializer.
    current = getattr(app.state, "auth_config", AuthConfig(set(), set()))
    app.state.auth_config = AuthConfig(
        authorized_users=set(authorized_users),
        admin_users=current.admin_users,
    )


def get_authorized_users(request: Request) -> set[str]:
    return get_auth_config(request).authorized_users


AuthorizedUsersDep = Annotated[set[str], Depends(get_authorized_users)]
