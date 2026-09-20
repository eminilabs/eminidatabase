from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import require_mf_operator
from mf_app.core.security import generate_random_password, hash_password
from mf_app.db.control_session import get_control_db
from mf_app.models.institution import MFInstitution
from mf_app.models.staff_user import MFStaffRole, MFStaffUser
from mf_app.schemas.institution import InstitutionCreate, InstitutionCreated, InstitutionResponse
from mf_app.services.jobs import enqueue

router = APIRouter(
    prefix="/institutions", tags=["institutions"], dependencies=[Depends(require_mf_operator)]
)


@router.post("", response_model=InstitutionCreated, status_code=status.HTTP_201_CREATED)
async def create_institution(
    payload: InstitutionCreate, db: AsyncSession = Depends(get_control_db)
) -> InstitutionCreated:
    existing = (
        await db.execute(select(MFInstitution).where(MFInstitution.slug == payload.slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug already in use")

    institution = MFInstitution(name=payload.name, slug=payload.slug)
    db.add(institution)
    await db.flush()

    # Created synchronously, not in the onboard_institution job — cf. app/services/
    # onboarding.py's docstring: a generated secret must be revealed exactly once,
    # in this direct response, never persisted in a job's result column.
    admin_password = generate_random_password()
    db.add(
        MFStaffUser(
            institution_id=institution.id,
            email=payload.admin_email,
            password_hash=hash_password(admin_password),
            role=MFStaffRole.INSTITUTION_ADMIN,
        )
    )

    job = await enqueue(
        db,
        type="onboard_institution",
        payload={
            "institution_id": str(institution.id),
            "region_code": payload.region_code,
            "currency": payload.currency,
        },
        institution_id=institution.id,
    )
    await db.commit()
    await db.refresh(institution)

    return InstitutionCreated(
        institution=InstitutionResponse.model_validate(institution),
        job_id=job.id,
        admin_email=payload.admin_email,
        admin_password=admin_password,
    )


@router.get("", response_model=list[InstitutionResponse])
async def list_institutions(db: AsyncSession = Depends(get_control_db)) -> list[MFInstitution]:
    result = await db.execute(select(MFInstitution))
    return list(result.scalars().all())
