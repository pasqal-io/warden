from fastapi import APIRouter

from ..models import StandardResponse
from ..models.system import QPU, QPUOperational
from ..samples import DUMMY_QPU_SPECS

router = APIRouter(prefix="/system")

@router.get("", response_model=StandardResponse[QPU])
async def get_system():
    return StandardResponse(
        code=200,
        message="None",
        data=QPU(specs=DUMMY_QPU_SPECS),
        status="OK"
    )

@router.get("/operational", response_model=StandardResponse[QPUOperational])
async def get_operational_status():
    return StandardResponse(
        code=200,
        message="None",
        data=QPUOperational(operational_status="UP"),
        status="OK"
    )
