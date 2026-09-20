"""Infra-level database operations — migration between nodes.

Platform-admin scoped like nodes.py/clusters.py, not org RBAC: which physical node
hosts a database is an infrastructure decision, and cahier des charges is explicit
that "le client ne doit pas avoir besoin de connaître le VPS sur lequel sa base
fonctionne" — so tenants never pick a target node themselves.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_platform_admin
from app.db.session import get_db
from app.models.database import Database, DatabaseStatus
from app.models.node import Node
from app.models.user import User
from app.schemas.database import DatabaseCreateAccepted, MigrateRequest
from app.services.audit import record_audit
from app.services.jobs import enqueue
from app.services.node_health import is_eligible_for_placement
from app.services.orchestrator import get_primary_node
from app.services.placement import fits_on_node

router = APIRouter(prefix="/databases", tags=["database-admin"])


@router.post(
    "/{database_id}/migrate",
    response_model=DatabaseCreateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def migrate_database(
    database_id: uuid.UUID,
    payload: MigrateRequest,
    admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> DatabaseCreateAccepted:
    database = await db.get(Database, database_id)
    if database is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    if database.status != DatabaseStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot migrate a database that is {database.status.value}",
        )

    target_node = await db.get(Node, payload.target_node_id)
    if target_node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target node not found")
    if not is_eligible_for_placement(target_node):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Target node is not currently healthy"
        )
    if str(target_node.region_id) != str(database.region_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cross-region migration is not supported — it would silently change "
            "the database's declared region/data residency",
        )

    current_node = await get_primary_node(db, database.cluster_id)
    if current_node.id == target_node.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Database is already on that node"
        )

    if not await fits_on_node(
        db,
        target_node,
        cpu_limit=database.cpu_limit,
        ram_limit_mb=database.ram_limit_mb,
        storage_limit_gb=database.storage_limit_gb,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Target node does not have enough free capacity for this database",
        )

    database.status = DatabaseStatus.MIGRATING
    job = await enqueue(
        db,
        type="migrate_database",
        payload={"database_id": str(database.id), "target_node_id": str(target_node.id)},
        resource_type="database",
        resource_id=database.id,
    )
    await record_audit(
        db,
        action="DATABASE_MIGRATION_REQUESTED",
        resource_type="database",
        resource_id=database.id,
        user_id=admin.id,
        after={"from_node_id": str(current_node.id), "to_node_id": str(target_node.id)},
    )
    await db.commit()
    await db.refresh(database)
    return DatabaseCreateAccepted(database=database, job_id=job.id)
