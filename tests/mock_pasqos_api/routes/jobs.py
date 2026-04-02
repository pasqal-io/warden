"""Mock PasqOS jobs API route"""

from fastapi import APIRouter, HTTPException

import mock_pasqos_api.db as db
from mock_pasqos_api.models import JSendResponse
from mock_pasqos_api.models.jobs import Job, JobCreation

router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(job_model: JobCreation) -> JSendResponse[Job]:
    new_job = db.create_job(job_model)
    # We don't really care about the message, only about the data
    return JSendResponse(code=200, message="OK.", data=new_job)


@router.get("/{uid}")
async def get_job(uid: int) -> JSendResponse[Job]:
    if not db.job_exists(uid):
        # TODO: improve PasqOS error mimicking
        raise HTTPException(400, "Bad request")
    job = db.get_job(uid)
    return JSendResponse(code=200, message="OK.", data=job)


@router.put("/{uid}/cancel")
async def cancel_job(uid: int) -> JSendResponse[Job]:
    if not db.job_exists(uid):
        # TODO: improve PasqOS error mimicking
        raise HTTPException(400, "Bad request")
    job = db.cancel_job(uid)
    return JSendResponse(code=200, message="OK.", data=job)
