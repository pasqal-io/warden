import json
import os
from datetime import datetime

from mock_qpu_api.models.jobs import Job, JobCreation, JobStatus
from mock_qpu_api.models.program import Program, ProgramStatus
from mock_qpu_api.samples import FAKE_RESULTS

FAKE_JOB_DB: dict[str, Job] = {}
FAKE_PROGRAM_DB: dict[str, Program] = {}

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
    FAKE_JOB_DB[new_uid] = new_job
    return new_job


def get_job(uid: int) -> Job | None:
    if uid not in FAKE_JOB_DB:
        return None
    job = FAKE_JOB_DB[uid]
    # Artificial job logic
    if job.status == JobStatus.PENDING:
        job.status = JobStatus.RUNNING
        job.start_datetime = datetime.now()
        update_program_status(uid=uid, status=ProgramStatus.RUNNING)
    elif job.status == JobStatus.RUNNING:
        result = run_qutip_job(job) if uses_qutip_backend() else FAKE_RESULTS
        job.status = JobStatus.DONE if result is not None else JobStatus.ERROR
        job.result = result
        job.end_datetime = datetime.now()
        program_status = (
            ProgramStatus.DONE if result is not None else ProgramStatus.ERROR
        )
        update_program_status(uid=uid, status=program_status)
    return job


def cancel_job(uid: int) -> Job:
    job = FAKE_JOB_DB[uid]
    job.status = JobStatus.CANCELED
    program = FAKE_PROGRAM_DB[job.program_id]
    program.status = ProgramStatus.CANCELED
    return job


############
# PROGRAMS #
############


def program_exists(uid):
    return uid in FAKE_PROGRAM_DB.keys()


def create_program(new_uid: int) -> None:
    # TODO: Check program satus at creation
    new_program = Program(uid=new_uid, status=ProgramStatus.CREATED)
    FAKE_PROGRAM_DB[new_uid] = new_program


def update_program_status(uid: int, status: ProgramStatus) -> None:
    if not program_exists(uid):
        # TODO: handle error
        return
    FAKE_PROGRAM_DB[uid].status = status


def uses_qutip_backend() -> bool:
    return os.environ.get("MOCK_QPU_API_BACKEND") == "qutip"


def run_qutip_job(job: Job) -> str | None:
    from pulser import Sequence
    from pulser_simulation import QutipBackendV2

    try:
        sequence = Sequence.from_abstract_repr(job.pulser_sequence)
        result = QutipBackendV2(sequence, mimic_qpu=True).run()
        return json.dumps(
            {"counter": dict(result.final_state.sample(num_shots=job.nb_run))}
        )
    except Exception:
        return None
