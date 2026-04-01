from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..db import FAKE_JOB_DB, FAKE_PROGRAM_DB
from ..models import StandardResponse
from ..models.jobs import Job, JobCreation, JobStatus
from ..models.program import Program, ProgramStatus
from ..samples import FAKE_RESULTS

router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(job_model: JobCreation) -> StandardResponse[Job]:
    keys = FAKE_JOB_DB.keys()
    if len(keys) == 0:
        new_uid = 0
    else:
        new_uid = int(max(FAKE_JOB_DB.keys())) + 1
    # Check program satus
    new_program = Program(uid=new_uid, status=ProgramStatus.CREATED)
    new_job = Job(
        uid=new_uid,
        datetime=datetime.now(),
        status=JobStatus.PENDING,
        nb_run=job_model.nb_run,
        pulser_sequence=job_model.pulser_sequence,
        created_datetime=datetime.now(),
        program_id=new_uid,
        context=job_model.context,
        batch_id=job_model.context.batch_id,
    )
    FAKE_PROGRAM_DB[new_uid] = new_program
    FAKE_JOB_DB[new_uid] = new_job
    return StandardResponse(code=200, message="Created job", data=new_job, status="OK")


@router.get("/{uid}")
async def get_job(uid: int) -> StandardResponse[Job]:
    if uid not in FAKE_JOB_DB.keys():
        raise HTTPException(404, "Job does not exist")
    # TODO implement job logic here
    job = FAKE_JOB_DB[uid]
    if job.status == JobStatus.PENDING:
        job.status = JobStatus.RUNNING
        job.start_datetime = datetime.now()
    elif job.status == JobStatus.RUNNING:
        job.status = JobStatus.DONE
        job.result = FAKE_RESULTS
        job.end_datetime = datetime.now()
    return StandardResponse(code=200, message="Found job", data=job, status="OK")


@router.put("/{uid}/cancel")
async def cancel_job(uid: int) -> StandardResponse[Job]:
    if uid not in FAKE_JOB_DB.keys():
        raise HTTPException(404, "Job does not exist")
    job = FAKE_JOB_DB[uid]
    job.status = JobStatus.CANCELED
    program = FAKE_PROGRAM_DB[job.program_id]
    program.status = ProgramStatus.CANCELED
    return StandardResponse(code=200, message="Job canceled", data=job, status="OK")
