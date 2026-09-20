"""Job handlers for backup, restore, and backup verification.

cf. docs/architecture/05-backup-ha-scaling.md. Mirrors the structure of
app/services/orchestrator.py: called by the worker with the Job already RUNNING,
a raised exception means "retry later".
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.backup import Backup, BackupStatus
from app.models.cluster import Cluster, ClusterStatus, ClusterTopology
from app.models.cluster_member import ClusterMember, ClusterMemberRole
from app.models.database import Database, DatabaseStatus
from app.models.database_credential import CredentialScope, DatabaseCredential
from app.models.database_event import DatabaseEvent
from app.models.job import Job
from app.models.region import Region
from app.services.agent_client import call_agent
from app.services.orchestrator import ROLE_NAME_PREFIX, get_primary_node
from app.services.placement import select_node_and_cluster
from app.services.secrets import encrypt_secret
from app.services.webhook_orchestrator import emit_event


def backup_storage_key(database_id: uuid.UUID, backup_id: uuid.UUID) -> str:
    return f"backups/{database_id}/{backup_id}.dump.enc"


async def execute_backup_database(db: AsyncSession, job: Job) -> dict:
    backup = await db.get(Backup, uuid.UUID(job.payload["backup_id"]))
    if backup is None:
        raise RuntimeError(f"Backup {job.payload['backup_id']} not found")
    if backup.status in (BackupStatus.COMPLETED, BackupStatus.VERIFIED):
        return {"already_completed": True}

    database = await db.get(Database, backup.database_id)
    if database is None or database.cluster_id is None:
        raise RuntimeError(f"Database {backup.database_id} is not in a backable state")

    node = await get_primary_node(db, database.cluster_id)
    backup.started_at = utcnow()

    resp = await call_agent(
        node,
        "POST",
        f"/v1/database/{database.physical_name}/backup",
        json={"storage_key": backup.storage_key},
        timeout=120.0,
    )
    body = resp.json()

    backup.status = BackupStatus.COMPLETED
    backup.size_bytes = body["size_bytes"]
    backup.completed_at = utcnow()
    await emit_event(db, job.organization_id, "backup.completed", {"backup_id": str(backup.id)})
    return {"size_bytes": body["size_bytes"]}


async def execute_restore_database(db: AsyncSession, job: Job) -> dict:
    target = await db.get(Database, uuid.UUID(job.payload["database_id"]))
    if target is None:
        raise RuntimeError(f"Database {job.payload['database_id']} not found")
    if target.status == DatabaseStatus.RUNNING and target.cluster_id:
        return {"already_running": True}

    backup = await db.get(Backup, uuid.UUID(job.payload["backup_id"]))
    if backup is None:
        raise RuntimeError(f"Backup {job.payload['backup_id']} not found")
    if backup.status not in (BackupStatus.COMPLETED, BackupStatus.VERIFIED):
        raise RuntimeError(f"Backup {backup.id} is not restorable (status={backup.status.value})")

    region = await db.get(Region, target.region_id)
    if region is None:
        raise RuntimeError(f"Database {target.id} references a missing region")

    decision = await select_node_and_cluster(
        db,
        region_code=region.code,
        isolation_level=target.isolation_level,
        cpu_limit=target.cpu_limit,
        ram_limit_mb=target.ram_limit_mb,
        storage_limit_gb=target.storage_limit_gb,
    )

    if decision.existing_cluster is not None:
        cluster = decision.existing_cluster
    else:
        cluster = Cluster(
            region_id=region.id,
            topology=ClusterTopology.SINGLE,
            shared=target.isolation_level.value == "shared",
            status=ClusterStatus.ACTIVE,
        )
        db.add(cluster)
        await db.flush()
        db.add(
            ClusterMember(
                cluster_id=cluster.id, node_id=decision.node.id, role=ClusterMemberRole.PRIMARY
            )
        )
        await db.flush()

    target.cluster_id = cluster.id

    role_name = f"{ROLE_NAME_PREFIX}{target.physical_name.removeprefix('db_')}"
    password = secrets.token_urlsafe(24)

    await call_agent(
        decision.node,
        "POST",
        f"/v1/database/{target.physical_name}/restore",
        json={"storage_key": backup.storage_key, "role_name": role_name, "password": password},
        timeout=120.0,
    )

    db.add(
        DatabaseCredential(
            database_id=target.id,
            role_name=role_name,
            encrypted_password=encrypt_secret(password),
            scope=CredentialScope.APP,
            is_primary=True,
        )
    )

    target.connection_host = decision.node.ip_address
    target.connection_port = decision.node.postgres_port
    target.status = DatabaseStatus.RUNNING

    db.add(
        DatabaseEvent(
            database_id=target.id,
            job_id=job.id,
            event_type="DATABASE_RESTORED",
            data={"backup_id": str(backup.id), "node_id": str(decision.node.id)},
        )
    )
    await emit_event(
        db,
        job.organization_id,
        "restore.completed",
        {"database_id": str(target.id), "backup_id": str(backup.id)},
    )

    return {"node_id": str(decision.node.id), "cluster_id": str(cluster.id)}


async def execute_verify_backup(db: AsyncSession, job: Job) -> dict:
    backup = await db.get(Backup, uuid.UUID(job.payload["backup_id"]))
    if backup is None:
        raise RuntimeError(f"Backup {job.payload['backup_id']} not found")
    if backup.status not in (BackupStatus.COMPLETED, BackupStatus.VERIFIED):
        return {"skipped": True, "reason": f"backup status is {backup.status.value}"}

    database = await db.get(Database, backup.database_id)
    if database is None or database.cluster_id is None:
        raise RuntimeError(f"Database {backup.database_id} has no node to verify against")

    node = await get_primary_node(db, database.cluster_id)
    resp = await call_agent(
        node,
        "POST",
        "/v1/verify-backup",
        json={"storage_key": backup.storage_key},
        timeout=120.0,
    )
    body = resp.json()

    backup.verified_at = utcnow()
    backup.verification_detail = body["detail"]
    backup.status = BackupStatus.VERIFIED if body["verified"] else BackupStatus.VERIFICATION_FAILED
    return body


BACKUP_HANDLERS = {
    "backup_database": execute_backup_database,
    "restore_database": execute_restore_database,
    "verify_backup": execute_verify_backup,
}
