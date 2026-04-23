import asyncio
from logging import getLogger

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from warden.api.routes.dependencies.auth import (
    MungeIdentity,
    munge_identity,
    verify_session,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_client
from warden.api.schemas.jobs import Job, JobCreate, JobResponse
from warden.api.utils.cudaq import normalize_job_sequence
from warden.lib.models.sessions import Session
from warden.lib.qpu_client import AsyncQPUClient, QPUClientRequestError

logger = getLogger(__name__)
router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(
    job: JobCreate,
    db: DBSessionDep,
    session: Session = Depends(verify_session),
    qpu_client: AsyncQPUClient = Depends(get_qpu_client),
) -> JobResponse:
    if isinstance(job.sequence, str):
        normalized_sequence = job.sequence
    else:
        try:
            qpu_specs = await qpu_client.get_specs()
        except QPUClientRequestError as exc:
            raise HTTPException(
                status_code=503,
                detail="Failed to fetch QPU specs.",
            ) from exc
        try:
            normalized_sequence = await asyncio.to_thread(
                normalize_job_sequence, job.sequence, qpu_specs
            )
        except (ValueError, TypeError, NotImplementedError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    new_job = Job(
        shots=job.shots,
        sequence=normalized_sequence,
        session_id=session.id,
    )
    db.add(new_job)
    await db.flush()
    await db.commit()
    logger.info(f"Created warden job {new_job.id} for slurm job {session.slurm_job_id}")
    return JobResponse.from_model(new_job)


@router.get("")
async def list_jobs(
    session: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
) -> list[JobResponse]:
    result = await session.execute(select(Job).where(Job.user_id == identity.uid))
    jobs = result.scalars().all()

    return [JobResponse.from_model(job) for job in jobs]


@router.get("/{id}")
async def get_job(
    id: int,
    session: DBSessionDep,
    identity: MungeIdentity = Depends(munge_identity),
) -> JobResponse:
    result = await session.execute(
        select(Job).where(Job.user_id == identity.uid, Job.id == id)
    )
    job = result.scalars().one_or_none()
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return JobResponse.from_model(job)
