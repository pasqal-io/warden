import json
import logging
import os
from datetime import datetime, timedelta

from mock_qpu_api.config import TimedConfig
from mock_qpu_api.models.jobs import Job, JobCreation, JobStatus
from mock_qpu_api.models.program import Program, ProgramStatus
from mock_qpu_api.samples import FAKE_PARTIAL_RESULTS, FAKE_RESULTS

FAKE_JOB_DB: dict[str, Job] = {}
FAKE_PROGRAM_DB: dict[str, Program] = {}

# Using the Uvicorn logger for easy logging setup
logger = logging.getLogger(f"uvicorn.{__name__}")

########
# JOBS #
########


def create_job(job_model: JobCreation) -> Job:
    keys = FAKE_JOB_DB.keys()
    if len(keys) == 0:
        new_uid = 0
    else:
        new_uid = int(max(FAKE_JOB_DB.keys())) + 1
    create_program(new_uid)

    current_time = datetime.now()
    new_job = Job(
        uid=new_uid,
        datetime=current_time,
        status=JobStatus.PENDING,
        nb_run=job_model.nb_run,
        pulser_sequence=job_model.pulser_sequence,
        created_datetime=current_time,
        program_id=new_uid,
        context=job_model.context,
        batch_id=job_model.context.batch_id,
    )

    FAKE_JOB_DB[str(new_uid)] = new_job
    return new_job


def fetch_job(uid: int) -> Job | None:
    """Fetch record from DB"""
    if str(uid) not in FAKE_JOB_DB:
        return None
    return FAKE_JOB_DB[str(uid)]


def get_job(uid: int, timed_config: TimedConfig) -> Job | None:
    """Implement GET jobs/uid route logic

    If the job UID is not present in the DB, return None.

    Getting a job that is in PENDING status "starts" it's execution by setting its status to RUNNING.

    When a job is in RUNNING status, it checks:
    - If the API is configured for a timed execution
        - The `timed_config` gives us the expected end time
        - If the job is expected to end before current time, it continues running.
    - Else the job immediately ends it's execution

    Job results are either mocked or emulated from Qutip depending on the API configuration.
    """

    if str(uid) not in FAKE_JOB_DB:
        return None
    job = FAKE_JOB_DB[str(uid)]

    current_time = datetime.now()

    # Artificial job logic with timing support
    if job.status == JobStatus.PENDING:
        job.status = JobStatus.RUNNING
        job.start_datetime = current_time
        update_program_status(uid=uid, status=ProgramStatus.RUNNING)
    elif job.status == JobStatus.RUNNING and (job.start_datetime is not None):
        # Check if job should keep running
        job_duration_s = job.nb_run * timed_config.shot_duration_s
        expected_end_time = job.start_datetime + timedelta(seconds=job_duration_s)
        if current_time < expected_end_time:
            job.result = FAKE_PARTIAL_RESULTS
            # Job is still running
            return job
        # Job should end
        if _uses_qutip_backend():
            result = _run_qutip_job(job)
        else:
            result = FAKE_RESULTS
        job.status = JobStatus.DONE if result is not None else JobStatus.ERROR
        job.result = result
        job.end_datetime = current_time
        program_status = (
            ProgramStatus.DONE if result is not None else ProgramStatus.ERROR
        )
        update_program_status(uid=uid, status=program_status)

        actual_duration = (job.end_datetime - job.start_datetime).total_seconds()
        logger.debug(f"Job {uid} completed after {actual_duration:.2f}s")

    return job


def cancel_job(uid: int) -> Job:
    job = FAKE_JOB_DB[str(uid)]
    job.status = JobStatus.CANCELED
    job.result = FAKE_PARTIAL_RESULTS
    program = FAKE_PROGRAM_DB[str(job.program_id)]
    program.status = ProgramStatus.CANCELED
    return job


############
# PROGRAMS #
############


def program_exists(uid: int):
    return str(uid) in FAKE_PROGRAM_DB.keys()


def create_program(new_uid: int) -> None:
    # TODO: Check program satus at creation
    new_program = Program(uid=new_uid, status=ProgramStatus.CREATED)
    FAKE_PROGRAM_DB[str(new_uid)] = new_program


def update_program_status(uid: int, status: ProgramStatus) -> None:
    if not program_exists(uid):
        # TODO: handle error
        return
    FAKE_PROGRAM_DB[str(uid)].status = status


def _uses_qutip_backend() -> bool:
    return "MOCK_QPU_API_EMUL" in os.environ


def _run_qutip_job(job: Job) -> str | None:
    from pulser import Sequence
    from pulser_simulation import QutipBackendV2

    try:
        sequence = Sequence.from_abstract_repr(job.pulser_sequence)
    except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
        logger.exception("Failed to deserialize pulser sequence")
        return None

    try:
        result = QutipBackendV2(sequence, mimic_qpu=True).run()
        return json.dumps(
            {"counter": dict(result.final_state.sample(num_shots=job.nb_run))}
        )
    except Exception:
        logger.exception("Failed to run Qutip simulation on pulser sequence")
        return None
