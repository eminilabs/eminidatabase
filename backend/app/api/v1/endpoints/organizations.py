from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.organization import (
    MembershipCreate,
    MembershipResponse,
    OrganizationCreate,
    OrganizationResponse,
)
from app.services.audit import record_audit
from app.services.billing import BILLING_PERIOD
from app.services.rbac import require_permission

DEFAULT_PLAN_NAME = "free"

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    existing = await db.execute(select(Organization).where(Organization.slug == payload.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")

    org = Organization(name=payload.name, slug=payload.slug)
    db.add(org)
    await db.flush()

    membership = Membership(
        user_id=current_user.id, organization_id=org.id, role=MembershipRole.OWNER
    )
    db.add(membership)

    # Every organization has exactly one Subscription from the moment it
    # exists (cf. docs/architecture/02 ERD) — defaults to the free plan so
    # nothing downstream (quota checks, billing) ever has to special-case a
    # missing subscription.
    default_plan = (
        await db.execute(select(Plan).where(Plan.name == DEFAULT_PLAN_NAME))
    ).scalar_one_or_none()
    if default_plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No '{DEFAULT_PLAN_NAME}' plan configured — seed it before accepting signups",
        )
    now = utcnow()
    db.add(
        Subscription(
            organization_id=org.id,
            plan_id=default_plan.id,
            current_period_start=now,
            current_period_end=now + BILLING_PERIOD,
        )
    )

    await record_audit(
        db,
        action="ORGANIZATION_CREATED",
        resource_type="organization",
        resource_id=org.id,
        organization_id=org.id,
        user_id=current_user.id,
        after={"name": org.name, "slug": org.slug},
    )
    await db.commit()
    await db.refresh(org)
    return OrganizationResponse.model_validate(org, from_attributes=True).model_copy(
        update={"role": MembershipRole.OWNER}
    )


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[OrganizationResponse]:
    result = await db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == current_user.id)
    )
    return [
        OrganizationResponse.model_validate(org, from_attributes=True).model_copy(
            update={"role": role}
        )
        for org, role in result.all()
    ]


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationResponse.model_validate(org, from_attributes=True).model_copy(
        update={"role": membership.role}
    )


@router.get("/{organization_id}/members", response_model=list[MembershipResponse])
async def list_members(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[Membership]:
    require_permission(membership.role, "org:read")
    result = await db.execute(
        select(Membership).where(Membership.organization_id == organization_id)
    )
    return list(result.scalars().all())


@router.post(
    "/{organization_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    organization_id: uuid.UUID,
    payload: MembershipCreate,
    request: Request,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Membership:
    require_permission(membership.role, "org:manage_members")

    target_user = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user is registered with that email",
        )

    existing = await db.execute(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == target_user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")

    new_membership = Membership(
        user_id=target_user.id, organization_id=organization_id, role=payload.role
    )
    db.add(new_membership)
    await record_audit(
        db,
        action="MEMBER_ADDED",
        resource_type="membership",
        organization_id=organization_id,
        user_id=current_user.id,
        after={"target_user_id": str(target_user.id), "role": payload.role.value},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(new_membership)
    return new_membership


@router.delete(
    "/{organization_id}/members/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove_member(
    organization_id: uuid.UUID,
    target_user_id: uuid.UUID,
    request: Request,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_permission(membership.role, "org:manage_members")

    target = (
        await db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == target_user_id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    if target.role == MembershipRole.OWNER:
        owners_count = (
            await db.execute(
                select(Membership).where(
                    Membership.organization_id == organization_id,
                    Membership.role == MembershipRole.OWNER,
                )
            )
        ).scalars().all()
        if len(owners_count) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner of the organization",
            )

    await db.delete(target)
    await record_audit(
        db,
        action="MEMBER_REMOVED",
        resource_type="membership",
        organization_id=organization_id,
        user_id=current_user.id,
        before={"target_user_id": str(target_user_id), "role": target.role.value},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
