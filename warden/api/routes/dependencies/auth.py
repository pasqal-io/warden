import asyncio
from dataclasses import dataclass
from logging import getLogger
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import UUID4
from sqlalchemy import select

from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.utils.munge import (
    MungeExpiredError,
    MungeReplayError,
    decode_munge,
)
from warden.lib.config.config import APIConfig
from warden.lib.models.sessions import Session

logger = getLogger(__name__)


@dataclass(frozen=True)
class AuthConfig:
    """Authentication/authorization policy configured for the API."""

    authorized_users: set[str]
    admin_users: set[str]
    munge_audience: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MungeIdentity:
    uid: str
    payload: bytes


def init_auth(app: FastAPI, api_config: APIConfig) -> None:
    """Initialize all API auth policy in one place."""
    auth_config = AuthConfig(
        authorized_users=set(api_config.authorized_users),
        admin_users=set(api_config.admin_users),
        munge_audience=frozenset(url.rstrip("/") for url in api_config.munge_audience),
    )
    app.state.auth_config = auth_config


def get_auth_config(request: Request) -> AuthConfig:
    """Return current auth policy."""
    auth_config = getattr(request.app.state, "auth_config", None)
    if auth_config is None:
        raise RuntimeError(
            "Auth config not initialized. init_auth(app, ...) was not called."
        )
    return auth_config


AuthConfigDep = Annotated[AuthConfig, Depends(get_auth_config)]
AdminUsersDep = Annotated[
    set[str], Depends(lambda config=Depends(get_auth_config): config.admin_users)
]
AuthorizedUsersDep = Annotated[
    set[str], Depends(lambda config=Depends(get_auth_config): config.authorized_users)
]


def ensure_bound_to_request(
    payload: bytes, request: Request, audience: frozenset[str]
) -> None:
    """Raise unless the credential was issued for this request to this Warden.

    A MUNGE credential carries the client's uid but not its destination, so a
    server that receives one (e.g. through a wrong Warden URL) could relay it here
    once. Clients sign "<METHOD> <URL>" as the payload; with munge_audience set,
    the URL must be one of those base URLs followed by the request path.
    """
    if not audience:
        return
    signed = payload.decode(errors="replace")
    method, _, url = signed.partition(" ")
    path = request.url.path
    if method != request.method or not any(url == base + path for base in audience):
        logger.warning(
            "Refused a MUNGE credential signed for %r on %s %s; "
            "accepted: '<METHOD> <base URL><path>' with base URLs %s",
            signed,
            request.method,
            path,
            sorted(audience),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MUNGE credential not issued for this request to this Warden",
        )


async def munge_identity(
    x_munge_cred: str | None = Header(
        default=None,
        alias="X-Munge-Cred",
        description=(
            "MUNGE credential of the caller (`munge -n`). With `api.munge_audience` "
            "set, its payload must be the request's method and URL: "
            '`munge -s "GET http://warden:4207/status"`.'
        ),
    ),
) -> MungeIdentity:
    if not x_munge_cred:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing MUNGE credential",
        )

    try:
        payload, uid = await asyncio.to_thread(decode_munge, x_munge_cred.encode())
        logger.debug(
            f"Successfully decoded munge token, uid {uid} payload {str(payload)}"
        )
    except MungeReplayError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MUNGE credential replayed",
        )
    except MungeExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MUNGE credential expired",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MUNGE decode failed",
        )

    return MungeIdentity(uid=str(uid), payload=payload)


async def request_identity(
    request: Request,
    config: AuthConfigDep,
    identity: Annotated[MungeIdentity, Depends(munge_identity)],
) -> MungeIdentity:
    """Return the caller's identity, if its credential was issued for this request."""
    ensure_bound_to_request(identity.payload, request, config.munge_audience)
    return identity


CurrentUserDep = Annotated[MungeIdentity, Depends(request_identity)]


async def require_admin(
    config: AuthConfigDep,
    identity: CurrentUserDep,
) -> MungeIdentity:
    if identity.uid not in config.admin_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint restricted to admin user.",
        )
    return identity


AdminUserDep = Annotated[MungeIdentity, Depends(require_admin)]


async def require_valid_session(
    db: DBSessionDep,
    identity: CurrentUserDep,
    session_id: UUID4 | None = Header(default=None, alias="X-Warden-Session"),
) -> Session:
    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing 'X-Warden-Session' header.",
        )
    result = await db.execute(select(Session).where(Session.id == session_id))
    session_record = result.scalar_one_or_none()
    if session_record is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid session.",
        )
    if session_record.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session has been revoked.",
        )
    if identity.uid != session_record.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session belongs to another user.",
        )
    return session_record


SessionDep = Annotated[Session, Depends(require_valid_session)]


def ensure_user_is_authorized(config: AuthConfig, user_id: str) -> None:
    """Raise unless user_id is allowed to receive sessions.

    Empty authorized_users means all users are allowed.
    """
    if config.authorized_users and user_id not in config.authorized_users:
        logger.info(f"Unauthorized user: {user_id} attempting to create a session.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User ID not authorized.",
        )
