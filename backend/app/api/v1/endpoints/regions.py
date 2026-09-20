from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_platform_admin
from app.db.session import get_db
from app.models.region import Region
from app.models.user import User
from app.schemas.region import RegionCreate, RegionResponse
from app.services.audit import record_audit

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("", response_model=list[RegionResponse])
async def list_regions(
    _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Region]:
    result = await db.execute(select(Region).where(Region.active.is_(True)))
    return list(result.scalars().all())


@router.post("", response_model=RegionResponse, status_code=status.HTTP_201_CREATED)
async def create_region(
    payload: RegionCreate,
    admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Region:
    existing = await db.execute(select(Region).where(Region.code == payload.code))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Region code already exists"
        )

    region = Region(code=payload.code, name=payload.name)
    db.add(region)
    await db.flush()
    await record_audit(
        db,
        action="REGION_CREATED",
        resource_type="region",
        resource_id=region.id,
        user_id=admin.id,
        after={"code": region.code, "name": region.name},
    )
    await db.commit()
    await db.refresh(region)
    return region
