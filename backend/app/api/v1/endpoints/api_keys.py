from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership
from app.core.security import generate_api_key
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.membership import Membership
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyResponse
from app.services.audit import record_audit
from app.services.rbac import require_permission

router = APIRouter(prefix="/organizations/{organization_id}/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    organization_id: uuid.UUID,
    payload: ApiKeyCreate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    require_permission(membership.role, "api_key:manage")

    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        organization_id=organization_id,
        name=payload.name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=payload.scopes,
    )
    db.add(api_key)
    await db.flush()
    await record_audit(
        db,
        action="API_KEY_CREATED",
        resource_type="api_key",
        resource_id=api_key.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after={"name": api_key.name, "key_prefix": prefix},
    )
    await db.commit()

    return ApiKeyCreated(
        id=api_key.id, name=api_key.name, key_prefix=api_key.key_prefix, api_key=full_key
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKey]:
    require_permission(membership.role, "api_key:manage")
    result = await db.execute(select(ApiKey).where(ApiKey.organization_id == organization_id))
    return list(result.scalars().all())


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_api_key(
    organization_id: uuid.UUID,
    api_key_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_permission(membership.role, "api_key:manage")
    api_key = await db.get(ApiKey, api_key_id)
    if api_key is None or str(api_key.organization_id) != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    api_key.revoked_at = dt.datetime.now(dt.UTC)
    await record_audit(
        db,
        action="API_KEY_REVOKED",
        resource_type="api_key",
        resource_id=api_key.id,
        organization_id=organization_id,
        user_id=current_user.id,
    )
    await db.commit()
