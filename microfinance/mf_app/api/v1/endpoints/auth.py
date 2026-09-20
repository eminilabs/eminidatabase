from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import get_current_staff_user, get_institution_by_slug
from mf_app.core.security import create_staff_access_token, verify_password
from mf_app.db.control_session import get_control_db
from mf_app.models.institution import MFInstitution
from mf_app.models.staff_user import MFStaffUser
from mf_app.schemas.auth import StaffLoginRequest, StaffLoginResponse, StaffMeResponse

router = APIRouter(prefix="/institutions/{institution_slug}/auth", tags=["auth"])


@router.post("/login", response_model=StaffLoginResponse)
async def login(
    payload: StaffLoginRequest,
    institution: MFInstitution = Depends(get_institution_by_slug),
    db: AsyncSession = Depends(get_control_db),
) -> StaffLoginResponse:
    staff = (
        await db.execute(
            select(MFStaffUser).where(
                MFStaffUser.institution_id == institution.id,
                MFStaffUser.email == payload.email,
            )
        )
    ).scalar_one_or_none()
    if staff is None or not staff.is_active or not verify_password(
        payload.password, staff.password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_staff_access_token(
        staff_user_id=staff.id, institution_id=institution.id, role=staff.role.value
    )
    return StaffLoginResponse(access_token=token)


@router.get("/me", response_model=StaffMeResponse)
async def me(staff: MFStaffUser = Depends(get_current_staff_user)) -> MFStaffUser:
    return staff
