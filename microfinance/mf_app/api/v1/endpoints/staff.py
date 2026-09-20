from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import (
    get_current_staff_user,
    get_tenant_db,
    require_active_institution,
)
from mf_app.core.security import hash_password
from mf_app.db.control_session import get_control_db
from mf_app.models.institution import MFInstitution
from mf_app.models.staff_user import MFStaffRole, MFStaffUser
from mf_app.models.tenant.agent import Agent
from mf_app.models.tenant.branch import Branch
from mf_app.schemas.staff import StaffCreate, StaffResponse
from mf_app.services.rbac import require_permission

router = APIRouter(prefix="/institutions/{institution_slug}/staff", tags=["staff"])


@router.post("", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: StaffCreate,
    institution: MFInstitution = Depends(require_active_institution),
    staff: MFStaffUser = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_control_db),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> MFStaffUser:
    require_permission(staff.role, "staff:manage")

    if payload.role == MFStaffRole.INSTITUTION_ADMIN and payload.branch_id is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="institution_admin must not have a branch"
        )
    if payload.role != MFStaffRole.INSTITUTION_ADMIN and payload.branch_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"{payload.role.value} requires a branch_id"
        )
    if payload.branch_id is not None and await tenant_db.get(Branch, payload.branch_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Branch not found")

    existing = (
        await db.execute(
            select(MFStaffUser).where(
                MFStaffUser.institution_id == institution.id,
                MFStaffUser.email == payload.email,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already in use")

    agent = Agent(branch_id=payload.branch_id, full_name=payload.full_name, role=payload.role)
    tenant_db.add(agent)
    await tenant_db.commit()
    await tenant_db.refresh(agent)

    new_staff = MFStaffUser(
        institution_id=institution.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        tenant_agent_id=agent.id,
    )
    db.add(new_staff)
    await db.commit()
    await db.refresh(new_staff)
    return new_staff


@router.get("", response_model=list[StaffResponse])
async def list_staff(
    institution: MFInstitution = Depends(require_active_institution),
    staff: MFStaffUser = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_control_db),
) -> list[MFStaffUser]:
    require_permission(staff.role, "staff:read")
    result = await db.execute(
        select(MFStaffUser).where(MFStaffUser.institution_id == institution.id)
    )
    return list(result.scalars().all())
