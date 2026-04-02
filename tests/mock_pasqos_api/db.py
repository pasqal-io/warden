from datetime import datetime

from mock_pasqos_api.models.jobs import Job, JobCreation, JobStatus
from mock_pasqos_api.models.program import Program, ProgramStatus
from mock_pasqos_api.samples import FAKE_RESULTS

FAKE_JOB_DB: dict[str, Job] = {}
FAKE_PROGRAM_DB: dict[str, Program] = {}


def create_job(job_model: JobCreation) -> Job:
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
    return new_job


def get_job(uid: int) -> Job:
    job = FAKE_JOB_DB[uid]
    if job.status == JobStatus.PENDING:
        job.status = JobStatus.RUNNING
        job.start_datetime = datetime.now()
    elif job.status == JobStatus.RUNNING:
        job.status = JobStatus.DONE
        job.result = FAKE_RESULTS
        job.end_datetime = datetime.now()
    return job


def cancel_job(uid: int) -> Job:
    job = FAKE_JOB_DB[uid]
    job.status = JobStatus.CANCELED
    program = FAKE_PROGRAM_DB[job.program_id]
    program.status = ProgramStatus.CANCELED
    return job


def job_exists(uid: int) -> bool:
    return uid in FAKE_JOB_DB.keys()
