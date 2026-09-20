"""Shared tenant-scoped lookups for every endpoint nested under
/organizations/{org}/projects/{project}/databases/{database}/... — one place
enforcing that a database can only ever be reached through its own project/org,
reused by databases.py, database_roles.py, database_sql.py, and database_ops.py.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Database
from app.models.project import Project


async def get_project_or_404(
    db: AsyncSession, organization_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    project = await db.get(Project, project_id)
    if project is None or str(project.organization_id) != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def get_database_or_404(
    db: AsyncSession, project_id: uuid.UUID, database_id: uuid.UUID
) -> Database:
    database = await db.get(Database, database_id)
    if database is None or str(database.project_id) != str(project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    return database


async def get_database_ids_for_organization(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every database ever created under any project of this org — including
    now-deleted ones, since usage recorded while a database existed still
    needs to be billed (cf. app/services/billing.py)."""
    result = await db.execute(
        select(Database.id)
        .join(Project, Project.id == Database.project_id)
        .where(Project.organization_id == organization_id)
    )
    return [row[0] for row in result.all()]
