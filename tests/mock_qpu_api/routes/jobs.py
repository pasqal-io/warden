"""Mock QPU jobs API route"""

from fastapi import APIRouter, HTTPException

import mock_qpu_api.db as db
from mock_qpu_api.models import JSendResponse
from mock_qpu_api.models.jobs import Job, JobCreation

router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(job_model: JobCreation) -> JSendResponse[Job]:
    new_job = db.create_job(job_model)
    # We don't really care about the message, only about the data
    return JSendResponse(code=200, message="OK.", data=new_job)


@router.get("/{uid}")
async def get_job(uid: int) -> JSendResponse[Job]:
    job = db.get_job(uid)
    if job is None:
        # TODO: improve QPU error mimicking
        raise HTTPException(400, "Bad request")
    return JSendResponse(code=200, message="OK.", data=job)


@router.put("/{uid}/cancel")
async def cancel_job(uid: int) -> JSendResponse[Job]:
    if db.get_job(uid) is None:
        # TODO: improve QPU error mimicking
        raise HTTPException(400, "Bad request")
    job = db.cancel_job(uid)
    return JSendResponse(code=200, message="OK.", data=job)
