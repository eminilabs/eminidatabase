from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership, require_active_subscription
from app.db.session import get_db
from app.models.database import Database, DatabaseStatus
from app.models.membership import Membership
from app.models.user import User
from app.schemas.database_metrics import DatabaseMetricsResponse
from app.schemas.database_schema import TableInfo
from app.schemas.extension import ExtensionInstall, ExtensionResponse
from app.services.agent_client import AgentRequestError, call_agent
from app.services.audit import record_audit
from app.services.database_lookup import get_database_or_404, get_project_or_404
from app.services.orchestrator import get_primary_node
from app.services.rbac import require_permission

router = APIRouter(
    prefix="/organizations/{organization_id}/projects/{project_id}/databases/{database_id}",
    tags=["database-ops"],
)


async def _require_running(
    db: AsyncSession, database_id: uuid.UUID, project_id: uuid.UUID
) -> Database:
    database = await get_database_or_404(db, project_id, database_id)
    if database.status != DatabaseStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database is {database.status.value}, not running",
        )
    return database


@router.get("/extensions", response_model=list[ExtensionResponse])
async def list_extensions(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ExtensionResponse]:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    database = await _require_running(db, database_id, project_id)

    node = await get_primary_node(db, database.cluster_id)
    resp = await call_agent(node, "GET", f"/v1/database/{database.physical_name}/extensions")
    return [ExtensionResponse(**e) for e in resp.json()]


@router.post("/extensions", status_code=status.HTTP_201_CREATED)
async def install_extension(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    payload: ExtensionInstall,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _subscription_active: None = Depends(require_active_subscription),
) -> dict:
    require_permission(membership.role, "database:extensions:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await _require_running(db, database_id, project_id)

    node = await get_primary_node(db, database.cluster_id)
    try:
        await call_agent(
            node,
            "POST",
            f"/v1/database/{database.physical_name}/extensions",
            json={"name": payload.name},
        )
    except AgentRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await record_audit(
        db,
        action="DATABASE_EXTENSION_INSTALLED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after={"extension": payload.name},
    )
    await db.commit()
    return {"status": "installed", "name": payload.name}


@router.delete(
    "/extensions/{extension_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def drop_extension(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    extension_name: str,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _subscription_active: None = Depends(require_active_subscription),
) -> None:
    require_permission(membership.role, "database:extensions:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await _require_running(db, database_id, project_id)

    node = await get_primary_node(db, database.cluster_id)
    try:
        await call_agent(
            node, "DELETE", f"/v1/database/{database.physical_name}/extensions/{extension_name}"
        )
    except AgentRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await record_audit(
        db,
        action="DATABASE_EXTENSION_DROPPED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
        before={"extension": extension_name},
    )
    await db.commit()


@router.get("/metrics", response_model=DatabaseMetricsResponse)
async def get_metrics(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> DatabaseMetricsResponse:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    database = await _require_running(db, database_id, project_id)

    node = await get_primary_node(db, database.cluster_id)
    resp = await call_agent(node, "GET", f"/v1/database/{database.physical_name}/metrics")
    return DatabaseMetricsResponse(**resp.json())


@router.get("/tables", response_model=list[TableInfo])
async def list_tables(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[TableInfo]:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    database = await _require_running(db, database_id, project_id)

    node = await get_primary_node(db, database.cluster_id)
    resp = await call_agent(node, "GET", f"/v1/database/{database.physical_name}/tables")
    return [TableInfo(**t) for t in resp.json()]
