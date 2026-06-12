import asyncio
from datetime import datetime
from logging import getLogger

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.post("/{id}/cancel")
async def delete_job(
    id: int,
    db_session: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
    client: AsyncQPUClient = Depends(get_qpu_client),
) -> JobResponse:
    # Start transaction context
    async with db_session.begin():
        # Lock row/db during transaction
        result = await db_session.execute(
            select(Job)
            .where(Job.user_id == str(identity.uid), Job.id == id)
            .with_for_update(of=Job)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(404, detail="Job not found")
        elif job.status in ("CANCELED", "DONE", "ERROR"):
            raise HTTPException(
                409, detail=f"Job with status '{job.status}' can't be canceled"
            )
        elif job.canceled_at is not None:
            raise HTTPException(
                409, detail="Job with status was already requested to be stopped"
            )
        job.canceled_at = datetime.now()
        # Not yet started by the worker
        if job.status == "PENDING" and (job.scheduled_at is None):
            logger.debug("Canceling job %s in DB", job.id)
            # Set job to cancel
            # await db_session.execute(
            #     update(Job).where(Job.id == job.id).values({"status": "CANCELED"})
            # )
            job.status = "CANCELED"
            # Releases nowait
            return JobResponse.from_model(job)

    logger.debug("Canceling job %s in QPU", job.id)
    # When running, tell scheduler to cancel
    backend_id = await _wait_for_created(db_session, job)
    await client.cancel_job(id=backend_id)
    # Return Job status at the moment of the cancelation request
    return JobResponse.from_model(job)


async def _wait_for_created(session: AsyncSession, job: Job) -> str:
    """Waiting for the job to be created on QPU"""
    # TODO: Timeout
    while job.backend_id is None:
        await session.refresh(job)
        await asyncio.sleep(0.5)
    return job.backend_id


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
