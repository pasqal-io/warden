from fastapi import APIRouter, Depends, HTTPException

from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_config
from warden.api.schemas.qpu_slots import QPUSlotsResponse
from warden.lib.config.config import QPUConfig
from warden.lib.session_lifecycle import active_qpu_slots

router = APIRouter(prefix="/qpu-slots")


@router.get("")
async def qpu_slots(
    db_session: DBSessionDep,
    qpu_config: QPUConfig = Depends(get_qpu_config),
) -> QPUSlotsResponse:
    """Report QPU slot capacity for external scheduler sensors."""
    if qpu_config.qpu_slots_total is None:
        raise HTTPException(status_code=404, detail="QPU slots are not configured.")
    used = await active_qpu_slots(db_session)
    total = qpu_config.qpu_slots_total
    return QPUSlotsResponse(
        qpu_slots_total=total,
        qpu_slots_used=used,
        qpu_slots_available=max(total - used, 0),
    )
