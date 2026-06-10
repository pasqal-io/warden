import asyncio
from logging import getLogger

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from warden.api.routes.dependencies.auth import (
    MungeIdentity,
    munge_identity,
    verify_session,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_client
from warden.api.schemas.jobs import (
    AHSSequence,
    Job,
    JobCreate,
    JobLogResponse,
    JobResponse,
    try_parse_AHSSequence,
)
from warden.api.utils.cudaq import normalize_cudaq_sequence
from warden.lib.models.sessions import Session
from warden.lib.qpu_client import AsyncQPUClient, QPUClientRequestError

logger = getLogger(__name__)
router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(
    job: JobCreate,
    db_session: DBSessionDep,
    session: Session = Depends(verify_session),
    qpu_client: AsyncQPUClient = Depends(get_qpu_client),
) -> JobResponse:
    """
    Create a new job

    JobCreate.sequence can accept strings of Pulser or AHS sequences
    \f
    We accept both Pulser and AHS sequences as sequence inputs for CUDA-Q support.
    AHS sequences are converted into Pulser sequences before storing in db.
    """
    sequence = try_parse_AHSSequence(job.sequence)
    if isinstance(sequence, AHSSequence):
        try:
            qpu_specs = await qpu_client.get_specs()
        except QPUClientRequestError as exc:
            raise HTTPException(
                status_code=503,
                detail="Failed to fetch QPU specs.",
            ) from exc
        try:
            sequence = await asyncio.to_thread(
                normalize_cudaq_sequence, sequence, qpu_specs
            )
        except (ValueError, TypeError, NotImplementedError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    new_job = Job(
        shots=job.shots,
        sequence=sequence,
        session_id=session.id,
    )
    db_session.add(new_job)
    await db_session.flush()
    await db_session.commit()
    logger.info(f"Created warden job {new_job.id} for slurm job {session.slurm_job_id}")
    return JobResponse.from_model(new_job)


@router.get("")
async def list_jobs(
    db_session: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
) -> list[JobResponse]:
    result = await db_session.execute(
        select(Job).where(Job.user_id == str(identity.uid))
    )
    jobs = result.scalars().all()

    return [JobResponse.from_model(job) for job in jobs]


@router.get("/{id}")
async def get_job(
    id: int,
    db_session: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
) -> JobResponse:
    result = await db_session.execute(
        select(Job).where(Job.user_id == str(identity.uid), Job.id == id)
    )
    job = result.scalars().one_or_none()
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return JobResponse.from_model(job)


@router.delete("/{id}")
async def delete_job(
    id: int,
    db_session: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
    client: AsyncQPUClient = Depends(get_qpu_client),
) -> JobResponse:
    result = await db_session.execute(
        select(Job).where(Job.user_id == str(identity.uid), Job.id == id)
    )
    job = result.scalars().one_or_none()
    if job is None:
        raise HTTPException(404, detail="Job not found")
    if job.status in ("CANCELED", "DONE", "ERROR"):
        # TODO: find appropriate exception
        raise HTTPException(
            404, detail=f"Job with status '{job.status}' can't be canceled"
        )
    if job.status == "PENDING":
        # Set job to cancel
        await db_session.execute(
            update(Job).where(Job.id == job.id).values({"status": "CANCELED"})
        )
    else:
        # If running, tell scheduler to cancel
        backend_id = job.backend_id
        if backend_id is None:
            # TODO: find appropriate exception
            raise HTTPException(500)
        client.cancel_job(id=backend_id)
    # TODO: return right data
    return JobResponse.from_model(job)


@router.get("/{id}/logs")
async def get_job_logs(
    id: int,
    db_session: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
) -> JobLogResponse:
    result = await db_session.execute(
        select(Job).where(Job.user_id == str(identity.uid), Job.id == id)
    )
    job = result.scalars().one_or_none()
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return JobLogResponse.from_model(job)
