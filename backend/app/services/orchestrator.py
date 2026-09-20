"""Database Orchestrator — turns a queued Job into real actions on a Data Plane
Agent. Cf. docs/architecture/03-database-orchestrator-et-agent.md.

Every function here is called by the worker (app/worker.py) with the Job already
marked RUNNING; a raised exception means "retry later" (app/services/jobs.py handles
backoff), a normal return means success.
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.cluster import Cluster, ClusterStatus, ClusterTopology
from app.models.cluster_member import ClusterMember, ClusterMemberRole
from app.models.database import Database, DatabaseStatus, IsolationLevel
from app.models.database_credential import CredentialScope, DatabaseCredential
from app.models.database_event import DatabaseEvent
from app.models.job import Job
from app.models.node import Node
from app.models.region import Region
from app.services.agent_client import AgentUnreachableError, call_agent
from app.services.placement import find_shared_cluster_on_node, select_node_and_cluster
from app.services.secrets import decrypt_secret, encrypt_secret
from app.services.webhook_orchestrator import emit_event

PHYSICAL_NAME_PREFIX = "db_"
ROLE_NAME_PREFIX = "u_"


def generate_physical_identifiers() -> tuple[str, str]:
    """A single random suffix ties the database and its role together while
    keeping both well under Postgres's 63-byte identifier limit."""
    suffix = uuid.uuid4().hex[:24]
    return f"{PHYSICAL_NAME_PREFIX}{suffix}", f"{ROLE_NAME_PREFIX}{suffix}"


async def get_primary_node(db: AsyncSession, cluster_id: str) -> Node:
    member = (
        await db.execute(
            select(ClusterMember).where(
                ClusterMember.cluster_id == cluster_id,
                ClusterMember.role == ClusterMemberRole.PRIMARY,
            )
        )
    ).scalar_one()
    node = await db.get(Node, member.node_id)
    if node is None:
        raise RuntimeError(f"Cluster {cluster_id} references a missing node")
    return node


async def get_or_create_cluster_on_node(
    db: AsyncSession, node: Node, *, region_id, isolation_level: IsolationLevel
) -> Cluster:
    """Shared by fresh provisioning (which lets the scorer pick the node) and
    migration (which pins one explicitly) — once a node is chosen, joining or
    creating its cluster works the same way either way."""
    if isolation_level == IsolationLevel.SHARED:
        existing = await find_shared_cluster_on_node(db, node.id)
        if existing is not None:
            return existing

    cluster = Cluster(
        region_id=region_id,
        topology=ClusterTopology.SINGLE,
        shared=isolation_level == IsolationLevel.SHARED,
        status=ClusterStatus.ACTIVE,
    )
    db.add(cluster)
    await db.flush()
    db.add(ClusterMember(cluster_id=cluster.id, node_id=node.id, role=ClusterMemberRole.PRIMARY))
    await db.flush()
    return cluster


async def execute_create_database(db: AsyncSession, job: Job) -> dict:
    database = await db.get(Database, uuid.UUID(job.payload["database_id"]))
    if database is None:
        raise RuntimeError(f"Database {job.payload['database_id']} not found")

    if database.status == DatabaseStatus.RUNNING and database.cluster_id:
        return {"already_running": True}  # safety net if a job is re-run

    region = await db.get(Region, database.region_id)
    if region is None:
        raise RuntimeError(f"Database {database.id} references a missing region")

    decision = await select_node_and_cluster(
        db,
        region_code=region.code,
        isolation_level=database.isolation_level,
        cpu_limit=database.cpu_limit,
        ram_limit_mb=database.ram_limit_mb,
        storage_limit_gb=database.storage_limit_gb,
    )

    cluster = decision.existing_cluster or await get_or_create_cluster_on_node(
        db, decision.node, region_id=region.id, isolation_level=database.isolation_level
    )
    database.cluster_id = cluster.id

    role_name = f"{ROLE_NAME_PREFIX}{database.physical_name.removeprefix(PHYSICAL_NAME_PREFIX)}"
    password = secrets.token_urlsafe(24)

    await call_agent(
        decision.node,
        "POST",
        "/v1/provision/database",
        json={
            "database_name": database.physical_name,
            "role_name": role_name,
            "password": password,
        },
    )

    db.add(
        DatabaseCredential(
            database_id=database.id,
            role_name=role_name,
            encrypted_password=encrypt_secret(password),
            scope=CredentialScope.APP,
            is_primary=True,
        )
    )

    database.connection_host = decision.node.ip_address
    database.connection_port = decision.node.postgres_port
    database.status = DatabaseStatus.RUNNING

    db.add(
        DatabaseEvent(
            database_id=database.id,
            job_id=job.id,
            event_type="DATABASE_RUNNING",
            data={"node_id": str(decision.node.id), "cluster_id": str(cluster.id)},
        )
    )
    await emit_event(
        db, job.organization_id, "database.created", {"database_id": str(database.id)}
    )

    return {
        "node_id": str(decision.node.id),
        "cluster_id": str(cluster.id),
        "connection_host": database.connection_host,
        "connection_port": database.connection_port,
    }


async def execute_delete_database(db: AsyncSession, job: Job) -> dict:
    database = await db.get(Database, uuid.UUID(job.payload["database_id"]))
    if database is None or database.status == DatabaseStatus.DELETED:
        return {"already_deleted": True}

    if database.cluster_id is not None:
        node = await get_primary_node(db, database.cluster_id)
        credential = (
            await db.execute(
                select(DatabaseCredential).where(
                    DatabaseCredential.database_id == database.id,
                    DatabaseCredential.scope == CredentialScope.APP,
                )
            )
        ).scalar_one_or_none()
        role_name = credential.role_name if credential else f"{ROLE_NAME_PREFIX}unknown"
        await call_agent(
            node,
            "DELETE",
            f"/v1/database/{database.physical_name}",
            params={"role_name": role_name},
        )

    database.status = DatabaseStatus.DELETED
    database.deleted_at = utcnow()
    db.add(DatabaseEvent(database_id=database.id, job_id=job.id, event_type="DATABASE_DELETED"))
    return {}


async def execute_suspend_database(db: AsyncSession, job: Job) -> dict:
    database = await db.get(Database, uuid.UUID(job.payload["database_id"]))
    if database is None:
        raise RuntimeError(f"Database {job.payload['database_id']} not found")
    if database.status == DatabaseStatus.SUSPENDED:
        return {"already_suspended": True}

    node = await get_primary_node(db, database.cluster_id)
    await call_agent(node, "POST", f"/v1/database/{database.physical_name}/suspend")

    database.status = DatabaseStatus.SUSPENDED
    db.add(DatabaseEvent(database_id=database.id, job_id=job.id, event_type="DATABASE_SUSPENDED"))
    return {}


async def execute_resume_database(db: AsyncSession, job: Job) -> dict:
    database = await db.get(Database, uuid.UUID(job.payload["database_id"]))
    if database is None:
        raise RuntimeError(f"Database {job.payload['database_id']} not found")
    if database.status == DatabaseStatus.RUNNING:
        return {"already_running": True}

    node = await get_primary_node(db, database.cluster_id)
    await call_agent(node, "POST", f"/v1/database/{database.physical_name}/resume")

    database.status = DatabaseStatus.RUNNING
    db.add(DatabaseEvent(database_id=database.id, job_id=job.id, event_type="DATABASE_RESUMED"))
    return {}


async def execute_migrate_database(db: AsyncSession, job: Job) -> dict:
    """Cf. docs/architecture/05-backup-ha-scaling.md §5.6. Reuses the Phase 5
    backup/restore machinery rather than a WAL-streaming clone: brief the
    quiesce-then-dump gives a guaranteed-consistent snapshot without needing
    per-database physical replication (which doesn't exist — replication in this
    platform runs at the whole-cluster level, cf. Phase 6). This means a short
    unavailability window during migration, not zero-downtime — documented, not
    hidden. The physical_name and role_name/password carry over unchanged, so the
    only thing that changes for the client is host/port (same as failover)."""
    database = await db.get(Database, uuid.UUID(job.payload["database_id"]))
    if database is None:
        raise RuntimeError(f"Database {job.payload['database_id']} not found")
    target_node = await db.get(Node, uuid.UUID(job.payload["target_node_id"]))
    if target_node is None:
        raise RuntimeError(f"Target node {job.payload['target_node_id']} not found")

    if database.cluster_id is None:
        raise RuntimeError(f"Database {database.id} has no current placement to migrate from")
    source_node = await get_primary_node(db, database.cluster_id)
    if source_node.id == target_node.id:
        return {"already_there": True}

    credential = (
        await db.execute(
            select(DatabaseCredential).where(
                DatabaseCredential.database_id == database.id,
                DatabaseCredential.is_primary.is_(True),
            )
        )
    ).scalar_one()
    password = decrypt_secret(credential.encrypted_password)

    # Blocks the tenant's role, not the admin connection this job's own dump needs
    # a moment later — cf. agent/app/postgres_admin.py's quiesce_for_migration
    # docstring for why suspend_database (ALLOW_CONNECTIONS false) can't be reused
    # here (a real bug caught by the Phase 7 live smoke test: it also locks out
    # our own pg_dump).
    await call_agent(
        source_node,
        "POST",
        f"/v1/database/{database.physical_name}/quiesce",
        json={"role_name": credential.role_name},
    )

    migration_key = f"migrations/{database.id}/{uuid.uuid4().hex}.dump.enc"
    await call_agent(
        source_node,
        "POST",
        f"/v1/database/{database.physical_name}/backup",
        json={"storage_key": migration_key},
        timeout=180.0,
    )

    await call_agent(
        target_node,
        "POST",
        f"/v1/database/{database.physical_name}/restore",
        json={
            "storage_key": migration_key,
            "role_name": credential.role_name,
            "password": password,
        },
        timeout=180.0,
    )

    old_cluster_id = database.cluster_id
    cluster = await get_or_create_cluster_on_node(
        db, target_node, region_id=database.region_id, isolation_level=database.isolation_level
    )
    database.cluster_id = cluster.id
    database.connection_host = target_node.ip_address
    database.connection_port = target_node.postgres_port
    database.status = DatabaseStatus.RUNNING

    # Only decommissioned now that the target is confirmed up and the cutover is
    # recorded — never destroy the source before the replacement works (§18).
    await call_agent(
        source_node,
        "DELETE",
        f"/v1/database/{database.physical_name}",
        params={"role_name": credential.role_name},
    )

    try:
        await call_agent(
            target_node, "DELETE", "/v1/backups", params={"storage_key": migration_key}
        )
    except AgentUnreachableError:
        pass  # best-effort cleanup of the transient migration snapshot

    db.add(
        DatabaseEvent(
            database_id=database.id,
            job_id=job.id,
            event_type="DATABASE_MIGRATED",
            data={
                "from_node_id": str(source_node.id),
                "to_node_id": str(target_node.id),
                "old_cluster_id": str(old_cluster_id),
            },
        )
    )

    return {"from_node_id": str(source_node.id), "to_node_id": str(target_node.id)}


HANDLERS = {
    "create_database": execute_create_database,
    "delete_database": execute_delete_database,
    "suspend_database": execute_suspend_database,
    "resume_database": execute_resume_database,
    "migrate_database": execute_migrate_database,
}
