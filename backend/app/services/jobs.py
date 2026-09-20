"""DB-backed job queue.

cf. docs/architecture/03 §"Jobs et idempotence" and §54 of the cahier des charges
(long operations run in workers, never inline in an HTTP request). This uses the
`jobs` table itself as the queue rather than Redis/Arq — the architecture doc names
Redis+Arq as the target transport for when multiple orchestrator workers need to
coordinate (Phase 7 scaling), but the functional requirements for Phase 3 (async
execution, persisted state, retries, idempotency) don't need a message broker, and a
DB-backed queue keeps the single-VPS Phase 3 deployment to one moving part instead of
two. Swapping the transport later doesn't change the `jobs` table or its consumers.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.job import Job, JobStatus

_BACKOFF_BASE_SECONDS = 5
_BACKOFF_MAX_SECONDS = 300


async def enqueue(
    db: AsyncSession,
    *,
    type: str,
    payload: dict,
    idempotency_key: str | None = None,
    organization_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
) -> Job:
    if idempotency_key is not None:
        existing = (
            await db.execute(select(Job).where(Job.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    job = Job(
        type=type,
        payload=payload,
        idempotency_key=idempotency_key,
        organization_id=organization_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.add(job)
    await db.flush()
    return job


async def claim_next_job(db: AsyncSession) -> Job | None:
    """Picks the oldest due job and marks it RUNNING in the same transaction.

    Not SKIP LOCKED-safe against concurrent workers (Postgres supports it, SQLite
    doesn't, and Phase 3 runs a single worker per docs/architecture/06 — the
    single-VPS phase). Coordinating multiple workers is a Phase 7 scaling concern.
    """
    now = utcnow()
    candidate = (
        await db.execute(
            select(Job)
            .where(
                Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]),
                Job.next_run_at <= now,
            )
            .order_by(Job.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if candidate is None:
        return None

    candidate.status = JobStatus.RUNNING
    candidate.attempts += 1
    candidate.started_at = now
    await db.flush()
    return candidate


async def mark_succeeded(db: AsyncSession, job: Job, result: dict | None = None) -> None:
    job.status = JobStatus.SUCCEEDED
    job.result = result
    job.completed_at = utcnow()
    job.error = None


async def mark_failed_or_retry(db: AsyncSession, job: Job, error: str) -> None:
    job.error = error[:2000]
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.completed_at = utcnow()
        return
    job.status = JobStatus.RETRYING
    backoff = min(_BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1)), _BACKOFF_MAX_SECONDS)
    job.next_run_at = utcnow() + dt.timedelta(seconds=backoff)
