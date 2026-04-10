from logging import getLogger

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from warden.api.routes.dependencies.auth import (
    MungeIdentity,
    munge_identity,
    verify_session,
)
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.schemas.jobs import Job, JobCreate, JobResponse
from warden.lib.models.sessions import Session

logger = getLogger(__name__)
router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(
    job: JobCreate,
    db: DBSessionDep,
    session: Session = Depends(verify_session),
) -> JobResponse:
    new_job = Job(
        shots=job.shots,
        sequence=job.sequence,
        session_id=session.id,
    )
    db.add(new_job)
    await db.flush()
    await db.commit()
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
