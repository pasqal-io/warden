"""Mock QPU Programs API route"""

from fastapi import APIRouter, HTTPException

from mock_qpu_api.db import FAKE_PROGRAM_DB, program_exists
from mock_qpu_api.models import JSendResponse
from mock_qpu_api.models.program import Program, ProgramStatus

router = APIRouter(prefix="/programs")


@router.get("/{uid}", response_model=JSendResponse[Program])
async def get_program(uid: int):
    if not program_exists(uid):
        # TODO: improve QPU error mimicking
        raise HTTPException(400, "Bad request")
    program = FAKE_PROGRAM_DB[uid]
    # TODO: Handle other cases
    program.status = ProgramStatus.RUNNING
    return JSendResponse(
        code=200,
        message="OK.",
        data=program,
    )
