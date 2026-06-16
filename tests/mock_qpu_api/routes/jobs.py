"""Mock QPU jobs API route"""

import logging

from fastapi import APIRouter, HTTPException, Request

import mock_qpu_api.db as db
from mock_qpu_api.models import JSendResponse
from mock_qpu_api.models.jobs import Job, JobCreation, JobStatus

logger = logging.getLogger(f"uvicorn.{__name__}")

router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(job_model: JobCreation, request: Request) -> JSendResponse[Job]:
    new_job = db.create_job(
        job_model, request.app.state.is_timed, request.app.state.shot_duration_s
    )
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
async def cancel_job(uid: int) -> JSendResponse:
    job = db.fetch_job(uid)
    if job is None:
        # TODO: improve QPU error mimicking
        raise HTTPException(400, "Bad request")
    if job.status in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELED):
        return JSendResponse(
            code=400,
            message="Not OK",
            data={"code": "3003", "data": {"status": "not cancellable"}},
        )
    job = db.cancel_job(uid)
    return JSendResponse(code=200, message="OK.", data=job)
