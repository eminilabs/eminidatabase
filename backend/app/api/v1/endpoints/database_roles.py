from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership
from app.core.security import generate_random_password
from app.db.session import get_db
from app.models.database import DatabaseStatus
from app.models.database_credential import CredentialScope, DatabaseCredential
from app.models.membership import Membership
from app.models.user import User
from app.schemas.database_role import RoleCreate, RoleCreated, RoleResponse
from app.services.agent_client import AgentRequestError, call_agent
from app.services.audit import record_audit
from app.services.database_lookup import get_database_or_404, get_project_or_404
from app.services.orchestrator import ROLE_NAME_PREFIX, get_primary_node
from app.services.rbac import require_permission
from app.services.secrets import encrypt_secret

router = APIRouter(
    prefix="/organizations/{organization_id}/projects/{project_id}/databases/{database_id}/roles",
    tags=["database-roles"],
)


def _to_response(credential: DatabaseCredential) -> RoleResponse:
    return RoleResponse(
        id=credential.id,
        name=credential.display_name,
        role_name=credential.role_name,
        scope=credential.scope,
        is_primary=credential.is_primary,
        created_at=credential.created_at,
        rotated_at=credential.rotated_at,
    )


@router.post("", response_model=RoleCreated, status_code=status.HTTP_201_CREATED)
async def create_role(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    payload: RoleCreate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoleCreated:
    require_permission(membership.role, "database:roles:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status != DatabaseStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot manage roles while database is {database.status.value}",
        )
    if payload.scope == CredentialScope.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ADMIN scope is reserved for the database's original owner role",
        )

    role_name = f"{ROLE_NAME_PREFIX}{uuid.uuid4().hex[:24]}"
    password = generate_random_password()

    node = await get_primary_node(db, database.cluster_id)
    try:
        await call_agent(
            node,
            "POST",
            f"/v1/database/{database.physical_name}/roles",
            json={"role_name": role_name, "password": password, "scope": payload.scope.value},
        )
    except AgentRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    credential = DatabaseCredential(
        database_id=database.id,
        role_name=role_name,
        display_name=payload.name,
        encrypted_password=encrypt_secret(password),
        scope=payload.scope,
    )
    db.add(credential)
    await db.flush()

    await record_audit(
        db,
        action="DATABASE_ROLE_CREATED",
        resource_type="database_credential",
        resource_id=credential.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after={"name": payload.name, "scope": payload.scope.value},
    )
    await db.commit()

    return RoleCreated(
        id=credential.id, name=payload.name, role_name=role_name, password=password
    )


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[RoleResponse]:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    await get_database_or_404(db, project_id, database_id)

    result = await db.execute(
        select(DatabaseCredential).where(DatabaseCredential.database_id == database_id)
    )
    return [_to_response(c) for c in result.scalars().all()]


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_role(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    credential_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_permission(membership.role, "database:roles:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    credential = await db.get(DatabaseCredential, credential_id)
    if credential is None or str(credential.database_id) != str(database_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if credential.is_primary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the database's original owner role",
        )

    node = await get_primary_node(db, database.cluster_id)
    try:
        await call_agent(
            node, "DELETE", f"/v1/database/{database.physical_name}/roles/{credential.role_name}"
        )
    except AgentRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    await db.delete(credential)
    await record_audit(
        db,
        action="DATABASE_ROLE_DELETED",
        resource_type="database_credential",
        resource_id=credential_id,
        organization_id=organization_id,
        user_id=current_user.id,
        before={"name": credential.display_name, "scope": credential.scope.value},
    )
    await db.commit()


@router.post("/{credential_id}/rotate", response_model=RoleCreated)
async def rotate_role(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    credential_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoleCreated:
    require_permission(membership.role, "database:roles:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    credential = await db.get(DatabaseCredential, credential_id)
    if credential is None or str(credential.database_id) != str(database_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    new_password = generate_random_password()
    node = await get_primary_node(db, database.cluster_id)
    try:
        await call_agent(
            node,
            "POST",
            f"/v1/database/{database.physical_name}/roles/{credential.role_name}/rotate",
            json={"password": new_password},
        )
    except AgentRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    credential.encrypted_password = encrypt_secret(new_password)
    credential.rotated_at = dt.datetime.now(dt.UTC)
    await record_audit(
        db,
        action="DATABASE_ROLE_ROTATED",
        resource_type="database_credential",
        resource_id=credential.id,
        organization_id=organization_id,
        user_id=current_user.id,
    )
    await db.commit()

    return RoleCreated(
        id=credential.id,
        name=credential.display_name or credential.role_name,
        role_name=credential.role_name,
        password=new_password,
    )
