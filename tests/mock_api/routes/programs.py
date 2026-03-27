from fastapi import APIRouter, HTTPException

from ..models import StandardResponse
from ..models.program import Program, ProgramStatus
from ..db import FAKE_PROGRAM_DB

router = APIRouter(prefix="/programs")

@router.get("/{uid}", response_model=StandardResponse[Program])
async def get_program(uid: int):
    if uid not in FAKE_PROGRAM_DB:
        raise HTTPException(404, "Program uid does not exist")
    program = FAKE_PROGRAM_DB[uid]
    # TODO: Handle other cases
    program.status = ProgramStatus.RUNNING
    return StandardResponse(
        code=200,
        message="Program found",
        data=program,
    )
