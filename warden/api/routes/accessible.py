from logging import getLogger

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from warden.api.routes.dependencies.auth import AdminUserDep
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_config
from warden.api.schemas.accessible import AccessibleResponse, UpdateAccessibleRequest
from warden.lib.config.config import QPUConfig
from warden.lib.models.accessible import (
    AccessibilitySettings,
    get_latest_accessibility_settings,
)
from warden.lib.models.sessions import Session, active_session_filter

logger = getLogger(__name__)
router = APIRouter(prefix="/accessible")


@router.get("")
async def is_accessible(
    db_session: DBSessionDep,
    qpu_config: QPUConfig = Depends(get_qpu_config),
) -> AccessibleResponse:
    """Warden endpoint for qrmi 'is_accessible' interface"""
    settings = await get_latest_accessibility_settings(db_session)
    slot_state = await qpu_slot_state(db_session, qpu_config)
    return AccessibleResponse(
        is_accessible=settings.is_accessible,
        message=settings.message,
        **slot_state,
    )


async def qpu_slot_state(db_session: DBSessionDep, qpu_config: QPUConfig) -> dict[str, int]:
    if qpu_config.qpu_slots_total is None:
        return {}
    result = await db_session.execute(
        select(func.coalesce(func.sum(Session.qpu_slots), 0)).where(
            active_session_filter()
        )
    )
    used = int(result.scalar_one())
    total = qpu_config.qpu_slots_total
    return {
        "qpu_slots_total": total,
        "qpu_slots_used": used,
        "qpu_slots_available": max(total - used, 0),
    }


@router.post("")
async def update_accessible(
    payload: UpdateAccessibleRequest,
    db_session: DBSessionDep,
    _admin: AdminUserDep,
) -> AccessibleResponse:
    """Update warden's /accessible endpoint"""
    # Create a new record for this change
    new_settings = AccessibilitySettings(
        is_accessible=payload.is_accessible, message=payload.message
    )

    db_session.add(new_settings)
    await db_session.commit()
    await db_session.refresh(new_settings)

    return AccessibleResponse(
        is_accessible=new_settings.is_accessible, message=new_settings.message
    )
