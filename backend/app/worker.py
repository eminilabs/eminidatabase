"""Database Orchestrator worker process.

Run as its own process, separate from the API (cf. docs/architecture §54 —
Job -> Queue -> Worker -> Orchestrator -> Data Plane, never inline in an HTTP
request handler):

    python -m app.worker

Polls the `jobs` table (see app/services/jobs.py for why that's the queue) and
dispatches to app/services/orchestrator.py.
"""

from __future__ import annotations

import asyncio
import logging

from app.db.session import AsyncSessionLocal
from app.models.backup import Backup, BackupStatus
from app.models.database import Database, DatabaseStatus
from app.models.database_event import DatabaseEvent
from app.models.job import Job, JobStatus
from app.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from app.services.backup_orchestrator import BACKUP_HANDLERS
from app.services.jobs import claim_next_job, mark_failed_or_retry, mark_succeeded
from app.services.orchestrator import HANDLERS
from app.services.webhook_orchestrator import WEBHOOK_HANDLERS, emit_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

POLL_INTERVAL_SECONDS = 1.0

ALL_HANDLERS = {**HANDLERS, **BACKUP_HANDLERS, **WEBHOOK_HANDLERS}


async def _mark_database_failed(db, job: Job) -> None:
    database = await db.get(Database, job.resource_id)
    if database is not None:
        database.status = DatabaseStatus.FAILED
        db.add(
            DatabaseEvent(
                database_id=database.id,
                job_id=job.id,
                event_type="DATABASE_JOB_FAILED",
                data={"job_type": job.type, "error": job.error},
            )
        )
    await emit_event(
        db, job.organization_id, "database.failed", {"database_id": str(job.resource_id)}
    )


async def _mark_backup_failed(db, job: Job) -> None:
    backup = await db.get(Backup, job.resource_id)
    if backup is not None:
        backup.status = BackupStatus.FAILED
        backup.error = job.error
    await emit_event(
        db, job.organization_id, "backup.failed", {"backup_id": str(job.resource_id)}
    )


async def _mark_webhook_delivery_failed(db, job: Job) -> None:
    delivery = await db.get(WebhookDelivery, job.resource_id)
    if delivery is not None:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.error = job.error


# The state machines (docs/architecture/02 §2.3, and Backup's own) have no edge for
# "stuck forever mid-operation", so a permanently-failed job needs to visibly flip
# its resource to a terminal FAILED state rather than leaving it stuck in-progress.
# verify_backup is deliberately absent: an infra failure while verifying (e.g. the
# agent being briefly unreachable) says nothing about whether the backup itself is
# good, so it must not flip a COMPLETED backup to FAILED — the scheduler just
# retries verification on its next pass.
_TERMINAL_FAILURE_HANDLERS = {
    "create_database": _mark_database_failed,
    "delete_database": _mark_database_failed,
    "suspend_database": _mark_database_failed,
    "resume_database": _mark_database_failed,
    "restore_database": _mark_database_failed,
    "migrate_database": _mark_database_failed,
    "backup_database": _mark_backup_failed,
    "deliver_webhook": _mark_webhook_delivery_failed,
}


async def run_once() -> bool:
    """Processes at most one job. Returns True if a job was found (regardless of
    outcome), so the caller can poll faster while work is available."""
    async with AsyncSessionLocal() as db:
        job = await claim_next_job(db)
        if job is None:
            await db.commit()
            return False
        await db.commit()

    job_id = job.id
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)  # reattach, this time in a live session
        handler = ALL_HANDLERS.get(job.type)
        try:
            if handler is None:
                raise ValueError(f"No handler registered for job type {job.type!r}")
            result = await handler(db, job)
            await mark_succeeded(db, job, result)
            logger.info("job %s (%s) succeeded", job.id, job.type)
        except Exception as exc:  # noqa: BLE001 — must never crash the worker loop
            await mark_failed_or_retry(db, job, str(exc))
            logger.warning("job %s (%s) failed: %s", job.id, job.type, exc)
            if job.status == JobStatus.FAILED:
                terminal_handler = _TERMINAL_FAILURE_HANDLERS.get(job.type)
                if terminal_handler is not None:
                    await terminal_handler(db, job)
        await db.commit()
    return True


async def main() -> None:
    logger.info("orchestrator worker started")
    while True:
        found = await run_once()
        if not found:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
