from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import require_mf_operator
from mf_app.db.control_session import get_control_db
from mf_app.models.job import MFJob
from mf_app.schemas.job import MFJobResponse

router = APIRouter(
    prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_mf_operator)]
)


@router.get("/{job_id}", response_model=MFJobResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_control_db)) -> MFJob:
    job = await db.get(MFJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
