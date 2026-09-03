import asyncio
from datetime import datetime, timezone
from logging import getLogger
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import CursorResult, case, select, update

from warden.api.routes.dependencies.auth import CurrentUserDep, SessionDep
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
from warden.lib.qpu_client import QPUClient, QPUClientRequestError

logger = getLogger(__name__)
router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(
    job: JobCreate,
    db_session: DBSessionDep,
    session: SessionDep,
    qpu_client: QPUClient = Depends(get_qpu_client),
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
    identity: CurrentUserDep,
) -> list[JobResponse]:
    result = await db_session.execute(select(Job).where(Job.user_id == identity.uid))
    jobs = result.scalars().all()

    return [JobResponse.from_model(job) for job in jobs]


@router.get("/{id}")
async def get_job(
    id: int,
    db_session: DBSessionDep,
    identity: CurrentUserDep,
) -> JobResponse:
    result = await db_session.execute(
        select(Job).where(Job.user_id == identity.uid, Job.id == id)
    )
    job = result.scalars().one_or_none()
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return JobResponse.from_model(job)


@router.post("/{id}/cancel")
async def cancel_job(
    id: int,
    db_session: DBSessionDep,
    identity: CurrentUserDep,
) -> JobResponse:
    async with db_session.begin():
        # Atomic claim: ownership and the cancelability guards are
        # evaluated by the DB against the live row in one statement, so
        # there's no read-then-write gap for a concurrent scheduler pickup
        cancel_job_stmt = (
            update(Job)
            .where(
                Job.id == id,
                Job.user_id == identity.uid,
                Job.status.not_in(("CANCELED", "DONE", "ERROR")),
                Job.canceled_at.is_(None),
            )
            .values(
                canceled_at=datetime.now(timezone.utc),
                status=case((Job.scheduled_at.is_(None), "CANCELED"), else_=Job.status),
            )
        )
        result = cast(
            CursorResult,
            await db_session.execute(cancel_job_stmt),
        )

        job = (
            await db_session.execute(
                select(Job).where(Job.id == id, Job.user_id == identity.uid)
            )
        ).scalar_one_or_none()

        if job is None:
            raise HTTPException(404, detail="Job not found")
        if result.rowcount == 0:
            if job.status in ("CANCELED", "DONE", "ERROR"):
                raise HTTPException(
                    409, detail=f"Job with status '{job.status}' can't be canceled"
                )
            raise HTTPException(
                409, detail="Job with status was already requested to be stopped"
            )
    return JobResponse.from_model(job)


@router.get("/{id}/logs")
async def get_job_logs(
    id: int,
    db_session: DBSessionDep,
    identity: CurrentUserDep,
) -> JobLogResponse:
    result = await db_session.execute(
        select(Job).where(Job.user_id == identity.uid, Job.id == id)
    )
    job = result.scalars().one_or_none()
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return JobLogResponse.from_model(job)
