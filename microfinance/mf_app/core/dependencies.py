from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.security import decode_staff_access_token, verify_operator_token
from mf_app.db.control_session import get_control_db
from mf_app.db.tenant_session import tenant_session_for_institution
from mf_app.models.institution import MFInstitution, MFInstitutionStatus
from mf_app.models.staff_user import MFStaffUser

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_mf_operator(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Gate for POST /institutions (onboarding) — internal ops only, not
    self-service (cf. docs/architecture/08 §8.11)."""
    if credentials is None or not verify_operator_token(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid operator token"
        )


async def get_institution_by_slug(
    institution_slug: str,
    db: AsyncSession = Depends(get_control_db),
) -> MFInstitution:
    institution = (
        await db.execute(select(MFInstitution).where(MFInstitution.slug == institution_slug))
    ).scalar_one_or_none()
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found"
        )
    return institution


async def require_active_institution(
    institution: MFInstitution = Depends(get_institution_by_slug),
) -> MFInstitution:
    if institution.status != MFInstitutionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Institution is {institution.status.value}, not active yet",
        )
    return institution


async def get_current_staff_user(
    institution: MFInstitution = Depends(get_institution_by_slug),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_control_db),
) -> MFStaffUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    payload = decode_staff_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    # Defense in depth (cf. §8.9): a token minted for institution A must be
    # structurally rejected on institution B's routes, even if slug resolution
    # elsewhere had a bug.
    if payload.institution_id != institution.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Token does not match institution"
        )
    staff = await db.get(MFStaffUser, payload.staff_user_id)
    if staff is None or not staff.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Staff account not found"
        )
    return staff


async def get_tenant_db(
    institution: MFInstitution = Depends(require_active_institution),
) -> AsyncGenerator[AsyncSession, None]:
    async for session in tenant_session_for_institution(institution):
        yield session
