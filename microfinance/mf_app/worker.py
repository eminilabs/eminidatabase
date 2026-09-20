"""Microfinance service worker process — same shape as backend/app/worker.py,
polling this service's own `mf_jobs` table (cf. docs/architecture/08 §8.5):

    python -m app.worker
"""

from __future__ import annotations

import asyncio
import logging

from mf_app.db.control_session import AsyncSessionLocal
from mf_app.models.institution import MFInstitution, MFInstitutionStatus
from mf_app.models.job import MFJob, MFJobStatus
from mf_app.services.jobs import claim_next_job, mark_failed_or_retry, mark_succeeded
from mf_app.services.onboarding import MF_HANDLERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mf_worker")

POLL_INTERVAL_SECONDS = 1.0


async def _mark_institution_failed(db, job: MFJob) -> None:
    institution = await db.get(MFInstitution, job.institution_id)
    if institution is not None:
        institution.status = MFInstitutionStatus.FAILED
        institution.failure_reason = job.error


_TERMINAL_FAILURE_HANDLERS = {
    "onboard_institution": _mark_institution_failed,
}


async def run_once() -> bool:
    async with AsyncSessionLocal() as db:
        job = await claim_next_job(db)
        if job is None:
            await db.commit()
            return False
        await db.commit()

    job_id = job.id
    async with AsyncSessionLocal() as db:
        job = await db.get(MFJob, job_id)
        handler = MF_HANDLERS.get(job.type)
        try:
            if handler is None:
                raise ValueError(f"No handler registered for job type {job.type!r}")
            result = await handler(db, job)
            await mark_succeeded(db, job, result)
            logger.info("job %s (%s) succeeded", job.id, job.type)
        except Exception as exc:  # noqa: BLE001 — must never crash the worker loop
            await mark_failed_or_retry(db, job, str(exc))
            logger.warning("job %s (%s) failed: %s", job.id, job.type, exc)
            if job.status == MFJobStatus.FAILED:
                terminal_handler = _TERMINAL_FAILURE_HANDLERS.get(job.type)
                if terminal_handler is not None:
                    await terminal_handler(db, job)
        await db.commit()
    return True


async def main() -> None:
    logger.info("microfinance worker started")
    while True:
        found = await run_once()
        if not found:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
