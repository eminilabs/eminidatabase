from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import get_current_staff_user, get_tenant_db
from mf_app.models.staff_user import MFStaffUser
from mf_app.models.tenant.branch import Branch
from mf_app.schemas.branch import BranchCreate, BranchResponse
from mf_app.services.rbac import require_permission

router = APIRouter(prefix="/institutions/{institution_slug}/branches", tags=["branches"])


@router.post("", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
async def create_branch(
    payload: BranchCreate,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Branch:
    require_permission(staff.role, "branches:manage")
    branch = Branch(name=payload.name, code=payload.code)
    tenant_db.add(branch)
    await tenant_db.commit()
    await tenant_db.refresh(branch)
    return branch


@router.get("", response_model=list[BranchResponse])
async def list_branches(
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> list[Branch]:
    require_permission(staff.role, "branches:read")
    result = await tenant_db.execute(select(Branch))
    return list(result.scalars().all())
