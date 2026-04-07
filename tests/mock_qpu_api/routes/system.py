"""Mock QPU Programs API route"""

from fastapi import APIRouter

from mock_qpu_api.models import JSendResponse
from mock_qpu_api.models.system import QPU, QPUOperational
from mock_qpu_api.samples import DUMMY_QPU_SPECS

router = APIRouter(prefix="/system")


@router.get("", response_model=JSendResponse[QPU])
async def get_system():
    return JSendResponse(code=200, data=QPU(specs=DUMMY_QPU_SPECS))


@router.get("/operational", response_model=JSendResponse[QPUOperational])
async def get_operational_status():
    return JSendResponse(
        code=200,
        data=QPUOperational(operational_status="UP"),
    )
