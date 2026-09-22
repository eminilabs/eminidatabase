from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership, require_active_subscription
from app.db.session import get_db
from app.models.database import Database, DatabaseStatus
from app.models.database_credential import CredentialScope, DatabaseCredential
from app.models.membership import Membership
from app.models.region import Region
from app.models.user import User
from app.schemas.database import (
    DatabaseConnectionResponse,
    DatabaseCreate,
    DatabaseCreateAccepted,
    DatabaseResize,
    DatabaseResponse,
)
from app.services.agent_client import AgentRequestError, call_agent
from app.services.audit import record_audit
from app.services.database_lookup import get_database_or_404, get_project_or_404
from app.services.jobs import enqueue
from app.services.orchestrator import generate_physical_identifiers, get_primary_node
from app.services.placement import fits_on_node
from app.services.quotas import QuotaExceededError, check_database_quota, get_organization_lock
from app.services.rbac import require_permission
from app.services.secrets import decrypt_secret

# Deterministic, documented resize formula for a shared-cluster database's only
# concretely enforceable resource guarantee (cf. docs/architecture/05 §5.4): there
# are no per-database cgroups on a shared Postgres instance, so "more CPU" is
# expressed as a larger connection budget instead of a cgroup quota.
CONNECTIONS_PER_CPU = 20

router = APIRouter(
    prefix="/organizations/{organization_id}/projects/{project_id}/databases",
    tags=["databases"],
)


@router.post("", response_model=DatabaseCreateAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_database(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: DatabaseCreate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _subscription_active: None = Depends(require_active_subscription),
) -> DatabaseCreateAccepted:
    require_permission(membership.role, "database:create")
    await get_project_or_404(db, organization_id, project_id)

    region = (
        await db.execute(
            select(Region).where(Region.code == payload.region_code, Region.active.is_(True))
        )
    ).scalar_one_or_none()
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or inactive region"
        )

    existing = await db.execute(
        select(Database).where(Database.project_id == project_id, Database.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A database with that name already exists in this project",
        )

    # Quota-check-then-insert must be atomic per organization, or two
    # concurrent requests can both pass the check before either commits (cf.
    # app/services/quotas.py's docstring on get_organization_lock — a real
    # race a Phase 11 concurrency test caught).
    async with get_organization_lock(organization_id):
        try:
            await check_database_quota(
                db,
                organization_id=organization_id,
                additional_storage_gb=payload.storage_limit_gb,
                additional_cpu=payload.cpu_limit,
            )
        except QuotaExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)
            ) from exc

        physical_name, _ = generate_physical_identifiers()
        database = Database(
            project_id=project_id,
            region_id=region.id,
            name=payload.name,
            physical_name=physical_name,
            isolation_level=payload.isolation_level,
            status=DatabaseStatus.CREATING,
            cpu_limit=payload.cpu_limit,
            ram_limit_mb=payload.ram_limit_mb,
            storage_limit_gb=payload.storage_limit_gb,
        )
        db.add(database)
        await db.flush()

        job = await enqueue(
            db,
            type="create_database",
            payload={"database_id": str(database.id)},
            idempotency_key=f"create_database:{database.id}",
            organization_id=organization_id,
            resource_type="database",
            resource_id=database.id,
        )

        await record_audit(
            db,
            action="DATABASE_CREATE_REQUESTED",
            resource_type="database",
            resource_id=database.id,
            organization_id=organization_id,
            user_id=current_user.id,
            after={
                "name": database.name,
                "region": region.code,
                "isolation": payload.isolation_level.value,
            },
        )
        await db.commit()
        await db.refresh(database)

    return DatabaseCreateAccepted(database=database, job_id=job.id)


@router.get("", response_model=list[DatabaseResponse])
async def list_databases(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[Database]:
    require_permission(membership.role, "database:read")
    await get_project_or_404(db, organization_id, project_id)
    result = await db.execute(
        select(Database).where(
            Database.project_id == project_id, Database.status != DatabaseStatus.DELETED
        )
    )
    return list(result.scalars().all())


@router.get("/{database_id}", response_model=DatabaseResponse)
async def get_database(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> Database:
    require_permission(membership.role, "database:read")
    await get_project_or_404(db, organization_id, project_id)
    return await get_database_or_404(db, project_id, database_id)


@router.delete("/{database_id}", response_model=DatabaseCreateAccepted)
async def delete_database(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatabaseCreateAccepted:
    require_permission(membership.role, "database:delete")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status == DatabaseStatus.DELETED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already deleted")

    database.status = DatabaseStatus.DELETING
    job = await enqueue(
        db,
        type="delete_database",
        payload={"database_id": str(database.id)},
        idempotency_key=f"delete_database:{database.id}",
        organization_id=organization_id,
        resource_type="database",
        resource_id=database.id,
    )
    await record_audit(
        db,
        action="DATABASE_DELETE_REQUESTED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(database)
    return DatabaseCreateAccepted(database=database, job_id=job.id)


@router.post("/{database_id}/suspend", response_model=DatabaseCreateAccepted)
async def suspend_database(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatabaseCreateAccepted:
    require_permission(membership.role, "database:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status != DatabaseStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot suspend a database in status {database.status.value}",
        )

    # No idempotency_key needed here: the RUNNING -> SUSPENDING transition above
    # already happened in this request's transaction, so a rapid duplicate request
    # sees SUSPENDING (not RUNNING) and is rejected by the status check above —
    # the state machine itself is the idempotency guard for suspend/resume.
    database.status = DatabaseStatus.SUSPENDING
    job = await enqueue(
        db,
        type="suspend_database",
        payload={"database_id": str(database.id)},
        organization_id=organization_id,
        resource_type="database",
        resource_id=database.id,
    )
    await record_audit(
        db,
        action="DATABASE_SUSPEND_REQUESTED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(database)
    return DatabaseCreateAccepted(database=database, job_id=job.id)


@router.post("/{database_id}/resume", response_model=DatabaseCreateAccepted)
async def resume_database(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatabaseCreateAccepted:
    require_permission(membership.role, "database:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status != DatabaseStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot resume a database in status {database.status.value}",
        )

    database.status = DatabaseStatus.UPDATING
    job = await enqueue(
        db,
        type="resume_database",
        payload={"database_id": str(database.id)},
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
    )
    await record_audit(
        db,
        action="DATABASE_RESUME_REQUESTED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(database)
    return DatabaseCreateAccepted(database=database, job_id=job.id)


@router.post("/{database_id}/resize", response_model=DatabaseResponse)
async def resize_database(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    payload: DatabaseResize,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Database:
    """Vertical resize. Synchronous, not a job — cf. Phase 4's roles/extensions
    endpoints for the same reasoning: this is a single fast agent call (a lone
    ALTER DATABASE), not a "long operation" under Règle 11."""
    require_permission(membership.role, "database:manage")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status != DatabaseStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot resize a database that is {database.status.value}",
        )

    node = await get_primary_node(db, database.cluster_id)
    fits = await fits_on_node(
        db,
        node,
        cpu_limit=payload.cpu_limit,
        ram_limit_mb=payload.ram_limit_mb,
        storage_limit_gb=payload.storage_limit_gb,
        exclude_database_id=database.id,
    )
    if not fits:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The requested size does not fit on this database's current node. "
                "A platform admin can migrate it to a larger node first."
            ),
        )

    connection_limit = payload.cpu_limit * CONNECTIONS_PER_CPU
    try:
        await call_agent(
            node,
            "POST",
            f"/v1/database/{database.physical_name}/connection-limit",
            json={"limit": connection_limit},
        )
    except AgentRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    before = {
        "cpu_limit": database.cpu_limit,
        "ram_limit_mb": database.ram_limit_mb,
        "storage_limit_gb": database.storage_limit_gb,
    }
    database.cpu_limit = payload.cpu_limit
    database.ram_limit_mb = payload.ram_limit_mb
    database.storage_limit_gb = payload.storage_limit_gb

    await record_audit(
        db,
        action="DATABASE_RESIZED",
        resource_type="database",
        resource_id=database.id,
        organization_id=organization_id,
        user_id=current_user.id,
        before=before,
        after={
            "cpu_limit": payload.cpu_limit,
            "ram_limit_mb": payload.ram_limit_mb,
            "storage_limit_gb": payload.storage_limit_gb,
        },
    )
    await db.commit()
    await db.refresh(database)
    return database


@router.get("/{database_id}/connection", response_model=DatabaseConnectionResponse)
async def get_database_connection(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    database_id: uuid.UUID,
    credential_id: uuid.UUID | None = Query(None),
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
    _subscription_active: None = Depends(require_active_subscription),
) -> DatabaseConnectionResponse:
    require_permission(membership.role, "database:connect")
    await get_project_or_404(db, organization_id, project_id)
    database = await get_database_or_404(db, project_id, database_id)

    if database.status not in (DatabaseStatus.RUNNING, DatabaseStatus.SUSPENDED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No connection available while database is {database.status.value}",
        )

    if credential_id is not None:
        credential = await db.get(DatabaseCredential, credential_id)
        if credential is None or str(credential.database_id) != str(database.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    else:
        credential = (
            await db.execute(
                select(DatabaseCredential).where(
                    DatabaseCredential.database_id == database.id,
                    DatabaseCredential.scope == CredentialScope.APP,
                )
            )
        ).scalar_one_or_none()
    if credential is None or not database.connection_host:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database has no provisioned credentials yet",
        )

    password = decrypt_secret(credential.encrypted_password)
    connection_string = (
        f"postgresql://{credential.role_name}:{password}@"
        f"{database.connection_host}:{database.connection_port}/{database.physical_name}"
        "?sslmode=require"
    )
    return DatabaseConnectionResponse(
        host=database.connection_host,
        port=database.connection_port,
        database=database.physical_name,
        username=credential.role_name,
        password=password,
        connection_string=connection_string,
    )
