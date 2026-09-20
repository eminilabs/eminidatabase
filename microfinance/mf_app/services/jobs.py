"""DB-backed job queue — identical rationale/shape to backend/app/services/jobs.py
(cf. docs/architecture/08 §8.5), a separate table for a separate deployable."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.timeutil import utcnow
from mf_app.models.job import MFJob, MFJobStatus

_BACKOFF_BASE_SECONDS = 5
_BACKOFF_MAX_SECONDS = 300


async def enqueue(
    db: AsyncSession,
    *,
    type: str,
    payload: dict,
    institution_id: uuid.UUID | None = None,
) -> MFJob:
    job = MFJob(type=type, payload=payload, institution_id=institution_id)
    db.add(job)
    await db.flush()
    return job


async def claim_next_job(db: AsyncSession) -> MFJob | None:
    now = utcnow()
    candidate = (
        await db.execute(
            select(MFJob)
            .where(
                MFJob.status.in_([MFJobStatus.QUEUED, MFJobStatus.RETRYING]),
                MFJob.next_run_at <= now,
            )
            .order_by(MFJob.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if candidate is None:
        return None

    candidate.status = MFJobStatus.RUNNING
    candidate.attempts += 1
    candidate.started_at = now
    await db.flush()
    return candidate


async def mark_succeeded(db: AsyncSession, job: MFJob, result: dict | None = None) -> None:
    job.status = MFJobStatus.SUCCEEDED
    job.result = result
    job.completed_at = utcnow()
    job.error = None


async def mark_failed_or_retry(db: AsyncSession, job: MFJob, error: str) -> None:
    job.error = error[:2000]
    if job.attempts >= job.max_attempts:
        job.status = MFJobStatus.FAILED
        job.completed_at = utcnow()
        return
    job.status = MFJobStatus.RETRYING
    backoff = min(_BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1)), _BACKOFF_MAX_SECONDS)
    job.next_run_at = utcnow() + dt.timedelta(seconds=backoff)
