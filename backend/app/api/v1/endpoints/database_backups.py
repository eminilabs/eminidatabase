from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership, require_active_subscription
from app.db.session import get_db
from app.models.backup import Backup, BackupStatus, BackupType
from app.models.database import Database, DatabaseStatus
from app.models.membership import Membership
from app.models.user import User
from app.schemas.backup import (
    BackupCreateAccepted,
    BackupPolicyUpdate,
    BackupResponse,
    RestoreAccepted,
    RestoreRequest,
)
from app.services.audit import record_audit
from app.services.backup_orchestrator import backup_storage_key
from app.services.database_lookup import get_database_or_404, get_project_or_404
from app.services.jobs import enqueue
from app.services.orchestrator import generate_physical_identifiers
from app.services.rbac import require_permission

router = APIRouter(
    prefix="/organizations/{organization_id}/projects/{project_id}/databases/{database_id}",
    tags=["database-backups"],
)


@router.post("/backups", response_model=BackupCreateAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_backup(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _subscription_active: None = Depends(require_active_subscription),
) -> BackupCreateAccepted:
    require_permission(membership.role, "database:backups:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status != DatabaseStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot back up a database that is {database.status.value}",
        )

    backup_id = uuid.uuid4()
    backup = Backup(
        id=backup_id,
        database_id=database.id,
        type=BackupType.MANUAL,
        storage_key=backup_storage_key(database.id, backup_id),
    )
    db.add(backup)
    await db.flush()

    job = await enqueue(
        db,
        type="backup_database",
        payload={"backup_id": str(backup.id)},
        organization_id=organization_id,
        resource_type="backup",
        resource_id=backup.id,
    )
    await record_audit(
        db,
        action="BACKUP_REQUESTED",
        resource_type="backup",
        resource_id=backup.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after={"database_id": str(database.id), "type": "manual"},
    )
    await db.commit()
    await db.refresh(backup)
    return BackupCreateAccepted(backup=backup, job_id=job.id)


@router.get("/backups", response_model=list[BackupResponse])
async def list_backups(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[Backup]:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    await get_database_or_404(db, project_id, database_id)

    result = await db.execute(
        select(Backup)
        .where(Backup.database_id == database_id, Backup.status != BackupStatus.PURGED)
        .order_by(Backup.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/backups/{backup_id}", response_model=BackupResponse)
async def get_backup(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    backup_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> Backup:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    await get_database_or_404(db, project_id, database_id)

    backup = await db.get(Backup, backup_id)
    if backup is None or str(backup.database_id) != str(database_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return backup


@router.post(
    "/backups/{backup_id}/restore",
    response_model=RestoreAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def restore_backup(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    backup_id: uuid.UUID,
    payload: RestoreRequest,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _subscription_active: None = Depends(require_active_subscription),
) -> RestoreAccepted:
    require_permission(membership.role, "database:backups:manage")
    await get_project_or_404(db, organization_id, project_id)
    source = await get_database_or_404(db, project_id, database_id)

    backup = await db.get(Backup, backup_id)
    if backup is None or str(backup.database_id) != str(database_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    if backup.status not in (BackupStatus.COMPLETED, BackupStatus.VERIFIED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Backup is not restorable (status={backup.status.value})",
        )

    existing_name = await db.execute(
        select(Database).where(Database.project_id == project_id, Database.name == payload.name)
    )
    if existing_name.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A database with that name already exists in this project",
        )

    physical_name, _ = generate_physical_identifiers()
    target = Database(
        project_id=project_id,
        region_id=source.region_id,
        name=payload.name,
        physical_name=physical_name,
        isolation_level=source.isolation_level,
        status=DatabaseStatus.RESTORING,
        cpu_limit=source.cpu_limit,
        ram_limit_mb=source.ram_limit_mb,
        storage_limit_gb=source.storage_limit_gb,
    )
    db.add(target)
    await db.flush()

    job = await enqueue(
        db,
        type="restore_database",
        payload={"database_id": str(target.id), "backup_id": str(backup.id)},
        idempotency_key=f"restore_database:{target.id}",
        organization_id=organization_id,
        resource_type="database",
        resource_id=target.id,
    )
    await record_audit(
        db,
        action="BACKUP_RESTORE_REQUESTED",
        resource_type="database",
        resource_id=target.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after={"source_database_id": str(source.id), "backup_id": str(backup.id)},
    )
    await db.commit()
    await db.refresh(target)
    return RestoreAccepted(database=target, job_id=job.id)


@router.get("/backup-policy", response_model=BackupPolicyUpdate)
async def get_backup_policy(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> BackupPolicyUpdate:
    require_permission(membership.role, "database:observe")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)
    if not database.backup_policy:
        return BackupPolicyUpdate(enabled=False)
    return BackupPolicyUpdate(**database.backup_policy)


@router.put("/backup-policy", response_model=BackupPolicyUpdate)
async def set_backup_policy(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    payload: BackupPolicyUpdate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _subscription_active: None = Depends(require_active_subscription),
) -> BackupPolicyUpdate:
    require_permission(membership.role, "database:backups:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    database.backup_policy = payload.model_dump()
    await record_audit(
        db,
        action="BACKUP_POLICY_UPDATED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after=database.backup_policy,
    )
    await db.commit()
    return payload
