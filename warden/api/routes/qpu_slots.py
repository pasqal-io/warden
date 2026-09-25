from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_config
from warden.api.schemas.qpu_slots import QPUSlotsResponse
from warden.lib.config.config import QPUConfig
from warden.lib.models.sessions import Session, active_session_filter

router = APIRouter(prefix="/qpu-slots")


@router.get("")
async def qpu_slots(
    db_session: DBSessionDep,
    qpu_config: QPUConfig = Depends(get_qpu_config),
) -> QPUSlotsResponse:
    """Report QPU slot capacity for external scheduler sensors."""
    if qpu_config.qpu_slots_total is None:
        raise HTTPException(status_code=404, detail="QPU slots are not configured.")
    result = await db_session.execute(
        select(func.coalesce(func.sum(Session.qpu_slots), 0)).where(
            active_session_filter()
        )
    )
    used = int(result.scalar_one())
    total = qpu_config.qpu_slots_total
    return QPUSlotsResponse(
        qpu_slots_total=total,
        qpu_slots_used=used,
        qpu_slots_available=max(total - used, 0),
    )
