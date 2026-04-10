import asyncio
from dataclasses import dataclass
from logging import getLogger

from fastapi import Depends, Header, HTTPException, status
from pydantic import UUID4
from sqlalchemy import select

from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.utils.munge import (
    MungeExpiredError,
    MungeReplayError,
    decode_munge,
)
from warden.lib.models.sessions import Session

logger = getLogger(__name__)


@dataclass(frozen=True)
class MungeIdentity:
    uid: int
    payload: bytes


async def munge_identity(
    x_munge_cred: str | None = Header(default=None, alias="X-Munge-Cred"),
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

    return MungeIdentity(uid=uid, payload=payload)


async def verify_root(identity: MungeIdentity = Depends(munge_identity)) -> None:
    # TODO: is the slurm UID necessarily 0?
    # Otherwise make it configurable
    if identity.uid != 0:
        raise HTTPException(
            status_code=403, detail="Endpoint restricted to slurm root user."
        )
    return identity


async def verify_session(
    db: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
    session_id: UUID4 | None = Header(default=None, alias="X-Warden-Session"),
) -> Session:
    if session_id is None:
        raise HTTPException(
            status_code=403, detail="Missing 'X-Warden-Session' header."
        )
    result = await db.execute(select(Session).where(Session.id == session_id))
    session_record = result.scalar_one_or_none()
    if session_record is None:
        raise HTTPException(status_code=403, detail="Invalid session.")
    if session_record.revoked_at is not None:
        raise HTTPException(status_code=403, detail="Session has been revoked.")
    if str(identity.uid) != session_record.user_id:
        raise HTTPException(status_code=403, detail="Session belongs to another user.")
    return session_record
