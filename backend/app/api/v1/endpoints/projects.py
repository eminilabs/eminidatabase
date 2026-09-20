from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership
from app.db.session import get_db
from app.models.membership import Membership
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.audit import record_audit
from app.services.rbac import require_permission

router = APIRouter(prefix="/organizations/{organization_id}/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    organization_id: uuid.UUID,
    payload: ProjectCreate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    require_permission(membership.role, "project:create")

    existing = await db.execute(
        select(Project).where(
            Project.organization_id == organization_id, Project.slug == payload.slug
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A project with that slug already exists in this organization",
        )

    project = Project(organization_id=organization_id, name=payload.name, slug=payload.slug)
    db.add(project)
    await db.flush()
    await record_audit(
        db,
        action="PROJECT_CREATED",
        resource_type="project",
        resource_id=project.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after={"name": project.name, "slug": project.slug},
    )
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    require_permission(membership.role, "project:read")
    result = await db.execute(select(Project).where(Project.organization_id == organization_id))
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> Project:
    require_permission(membership.role, "project:read")
    project = await db.get(Project, project_id)
    if project is None or str(project.organization_id) != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_project(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_permission(membership.role, "project:delete")
    project = await db.get(Project, project_id)
    if project is None or str(project.organization_id) != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await db.delete(project)
    await record_audit(
        db,
        action="PROJECT_DELETED",
        resource_type="project",
        resource_id=project.id,
        organization_id=organization_id,
        user_id=current_user.id,
        before={"name": project.name, "slug": project.slug},
    )
    await db.commit()
