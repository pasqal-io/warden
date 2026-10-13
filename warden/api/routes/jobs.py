import asyncio
from datetime import datetime, timezone
from logging import getLogger
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import CursorResult, case, func, select, update

from warden.api.routes.dependencies.auth import CurrentUserDep, SessionDep
from warden.api.routes.dependencies.db import DBSessionDep
from warden.api.routes.dependencies.qpu_client import get_qpu_client
from warden.api.routes.dependencies.session_config import SessionConfigDep
from warden.api.schemas.jobs import (
    AHSSequence,
    Job,
    JobCreate,
    JobLogResponse,
    JobResponse,
    try_parse_AHSSequence,
)
from warden.api.utils.cudaq import normalize_cudaq_sequence
from warden.lib.models import Session
from warden.lib.models.sessions import active_session_filter
from warden.lib.qpu_client import QPUClient, QPUClientRequestError
from warden.lib.session_lifecycle import idle_deadline

logger = getLogger(__name__)
router = APIRouter(prefix="/jobs")


@router.post("")
async def create_job(
    job: JobCreate,
    db_session: DBSessionDep,
    session: SessionDep,
    session_config: SessionConfigDep,
    qpu_client: QPUClient = Depends(get_qpu_client),
) -> JobResponse:
    """
    Create a new job

    JobCreate.sequence can accept strings of Pulser or AHS sequences
    \f
    We accept both Pulser and AHS sequences as sequence inputs for CUDA-Q support.
    AHS sequences are converted into Pulser sequences before storing in db.
    """
    # Release the session row locked by SessionDep while the sequence is
    # prepared, which may call the QPU. It is locked again before the insert.
    await db_session.commit()

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

    # Lock the session again so the job cannot be added after a concurrent
    # revocation canceled the session's jobs.
    session = (
        await db_session.execute(
            select(Session).where(Session.id == session.id).with_for_update(of=Session)
        )
    ).scalar_one()
    if session.revoked_at is not None:
        await db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session has been revoked.",
        )
    await _catch_up_scheduler_vruntime(db_session, session)
    new_job = Job(
        shots=job.shots,
        sequence=sequence,
        session_id=session.id,
    )
    db_session.add(new_job)
    session.idle_expires_at = idle_deadline(session_config)
    await db_session.flush()
    await db_session.commit()
    logger.info(
        "Created warden job %s for scheduler job %s",
        new_job.id,
        session.scheduler_job_id,
    )
    return JobResponse.from_model(new_job)


async def _catch_up_scheduler_vruntime(
    db_session: DBSessionDep, session: Session
) -> None:
    """Move a session that becomes runnable up to the other runnable sessions.

    WEIGHTED_FIFO orders sessions by scheduler_vruntime. A new or long idle
    session would otherwise keep a low value and take many turns in a row.
    """
    runnable = Job.status.in_(("PENDING", "RUNNING"))
    has_runnable_job = (
        await db_session.execute(
            select(Job.id).where(Job.session_id == session.id, runnable).limit(1)
        )
    ).scalar_one_or_none()
    if has_runnable_job is not None:
        return
    floor = (
        await db_session.execute(
            select(func.min(Session.scheduler_vruntime))
            .join(Job, Job.session_id == Session.id)
            .where(Session.id != session.id, runnable, active_session_filter())
        )
    ).scalar_one_or_none()
    if floor is not None and floor > session.scheduler_vruntime:
        session.scheduler_vruntime = floor


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
    session_config: SessionConfigDep,
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
    if job.scheduled_at is None:
        # Canceled before the worker picked it up: the session is idle again.
        # Separate transaction so the session is never locked after the job.
        async with db_session.begin():
            await db_session.execute(
                update(Session)
                .where(Session.id == job.session_id)
                .values(idle_expires_at=idle_deadline(session_config))
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
