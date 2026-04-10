from logging import getLogger

from fastapi import APIRouter, Depends

from warden.api.routes.dependencies.auth import verify_root
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.schemas.accessible import AccessibleResponse, UpdateAccessibleRequest
from warden.lib.models.accessible import (
    AccessibilitySettings,
    get_latest_accessibility_settings,
)

logger = getLogger(__name__)
router = APIRouter(prefix="/accessible")


@router.get("")
async def is_accessible(db_session: DBSessionDep) -> AccessibleResponse:
    """Warden endpoint for qrmi 'is_accessible' interface"""
    settings = await get_latest_accessibility_settings(db_session)
    return AccessibleResponse(
        is_accessible=settings.is_accessible, message=settings.message
    )


@router.post("")
async def update_accessible(
    payload: UpdateAccessibleRequest,
    db_session: DBSessionDep,
    _=Depends(verify_root),
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
