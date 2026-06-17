from typing import Annotated

from fastapi import Depends, FastAPI, Request

from warden.api.routes.dependencies.auth import AuthConfig, get_auth_config


def init_admin_users(app: FastAPI, admin_users: list[str]) -> None:
    # Compatibility shim. Prefer init_auth(app, config.api).
    current = getattr(app.state, "auth_config", AuthConfig(set(), set()))
    app.state.auth_config = AuthConfig(
        authorized_users=current.authorized_users,
        admin_users=set(admin_users),
    )


def get_admin_users(request: Request) -> set[str]:
    return get_auth_config(request).admin_users


AdminUsersDep = Annotated[set[str], Depends(get_admin_users)]
