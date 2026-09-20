from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership
from app.db.session import get_db
from app.models.database import DatabaseStatus
from app.models.database_credential import CredentialScope, DatabaseCredential
from app.models.membership import Membership
from app.models.query_execution import QueryExecution
from app.models.saved_query import SavedQuery
from app.models.user import User
from app.schemas.sql import (
    QueryExecutionResponse,
    SavedQueryCreate,
    SavedQueryResponse,
    SqlExecuteRequest,
    SqlExecuteResponse,
)
from app.services.audit import record_audit
from app.services.database_lookup import get_database_or_404, get_project_or_404
from app.services.rbac import require_permission
from app.services.sql_editor import execute_query

router = APIRouter(
    prefix="/organizations/{organization_id}/projects/{project_id}/databases/{database_id}/sql",
    tags=["sql-editor"],
)


@router.post("/execute", response_model=SqlExecuteResponse)
async def execute_sql(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    payload: SqlExecuteRequest,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SqlExecuteResponse:
    require_permission(membership.role, "database:sql:execute")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status != DatabaseStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot run queries while database is {database.status.value}",
        )

    if payload.role_id is not None:
        credential = await db.get(DatabaseCredential, payload.role_id)
        if credential is None or str(credential.database_id) != str(database_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    else:
        credential = (
            await db.execute(
                select(DatabaseCredential).where(
                    DatabaseCredential.database_id == database_id,
                    DatabaseCredential.scope == CredentialScope.APP,
                )
            )
        ).scalar_one_or_none()
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Database has no usable credentials"
            )

    result = await execute_query(database, credential, payload.query)

    history = QueryExecution(
        database_id=database.id,
        user_id=current_user.id,
        query_text=payload.query,
        status=result.status,
        row_count=result.row_count if result.status == "succeeded" else None,
        duration_ms=result.duration_ms,
        error=result.error,
    )
    db.add(history)
    await record_audit(
        db,
        action="SQL_QUERY_EXECUTED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
        result="success" if result.status == "succeeded" else "failure",
        after={"query": payload.query[:500], "role": credential.role_name},
    )
    await db.commit()

    return SqlExecuteResponse(
        status=result.status,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        duration_ms=result.duration_ms,
        error=result.error,
    )


@router.get("/history", response_model=list[QueryExecutionResponse])
async def get_history(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    limit: int = 50,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[QueryExecution]:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    await get_database_or_404(db, project_id, database_id)

    result = await db.execute(
        select(QueryExecution)
        .where(QueryExecution.database_id == database_id)
        .order_by(QueryExecution.created_at.desc())
        .limit(min(limit, 200))
    )
    return list(result.scalars().all())


@router.post(
    "/saved-queries", response_model=SavedQueryResponse, status_code=status.HTTP_201_CREATED
)
async def create_saved_query(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    payload: SavedQueryCreate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedQuery:
    require_permission(membership.role, "database:sql:execute")
    await get_project_or_404(db, organization_id, project_id)
    await get_database_or_404(db, project_id, database_id)

    saved = SavedQuery(
        database_id=database_id,
        user_id=current_user.id,
        name=payload.name,
        query_text=payload.query,
    )
    db.add(saved)
    await db.commit()
    await db.refresh(saved)
    return saved


@router.get("/saved-queries", response_model=list[SavedQueryResponse])
async def list_saved_queries(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SavedQuery]:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    await get_database_or_404(db, project_id, database_id)

    result = await db.execute(select(SavedQuery).where(SavedQuery.database_id == database_id))
    return list(result.scalars().all())


@router.delete(
    "/saved-queries/{saved_query_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_saved_query(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_permission(membership.role, "database:sql:execute")
    await get_project_or_404(db, organization_id, project_id)
    await get_database_or_404(db, project_id, database_id)

    saved = await db.get(SavedQuery, saved_query_id)
    if saved is None or str(saved.database_id) != str(database_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found")

    await db.delete(saved)
    await db.commit()
