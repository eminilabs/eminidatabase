"""High availability: attaching replicas to a cluster and failover.

cf. docs/architecture/05-backup-ha-scaling.md §5.3. Replica *provisioning* (the
initial pg_basebackup clone) is a day-0 infrastructure bootstrap step done once,
outside the running platform (cf. agent/app/replication.py's docstring) — this
module's job starts once a node is already streaming as a standby: adopting it into
cluster tracking, monitoring it, and promoting it if the primary goes down.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.cluster import Cluster
from app.models.cluster_event import ClusterEvent
from app.models.cluster_member import ClusterMember, ClusterMemberRole
from app.models.database import Database, DatabaseStatus
from app.models.node import Node
from app.services.agent_client import AgentUnreachableError, call_agent


class NoHealthyReplicaError(Exception):
    pass


async def get_member_replication_status(node: Node) -> dict:
    resp = await call_agent(node, "GET", "/v1/replication/status", timeout=10.0)
    return resp.json()


async def add_replica(db: AsyncSession, cluster: Cluster, node: Node) -> ClusterMember:
    """Adopts an already-streaming standby into cluster tracking. Refuses to
    attach a node that isn't actually replicating — this is a safety check, not a
    provisioning step (cf. module docstring)."""
    status = await get_member_replication_status(node)
    if status.get("role") != "standby":
        raise ValueError(
            f"Node {node.id} does not report as a standby (role={status.get('role')!r}); "
            "it must already be streaming from this cluster's primary before it can "
            "be attached"
        )

    member = ClusterMember(
        cluster_id=cluster.id,
        node_id=node.id,
        role=ClusterMemberRole.REPLICA,
        replication_lag_bytes=status.get("lag_bytes"),
    )
    db.add(member)
    await db.flush()
    db.add(
        ClusterEvent(
            cluster_id=cluster.id,
            event_type="REPLICA_ATTACHED",
            data={"node_id": str(node.id), "lag_bytes": status.get("lag_bytes")},
        )
    )
    return member


async def refresh_replica_lag(db: AsyncSession, cluster: Cluster) -> list[ClusterMember]:
    members = (
        (
            await db.execute(
                select(ClusterMember).where(
                    ClusterMember.cluster_id == cluster.id,
                    ClusterMember.role == ClusterMemberRole.REPLICA,
                )
            )
        )
        .scalars()
        .all()
    )
    for member in members:
        node = await db.get(Node, member.node_id)
        try:
            status = await get_member_replication_status(node)
            if status.get("role") == "standby":
                member.replication_lag_bytes = status.get("lag_bytes")
        except AgentUnreachableError:
            continue
    return members


async def execute_failover(
    db: AsyncSession, cluster_id: uuid.UUID, *, automatic: bool
) -> dict:
    cluster = await db.get(Cluster, cluster_id)
    if cluster is None:
        raise ValueError(f"Cluster {cluster_id} not found")

    members = (
        (await db.execute(select(ClusterMember).where(ClusterMember.cluster_id == cluster_id)))
        .scalars()
        .all()
    )
    primary_member = next((m for m in members if m.role == ClusterMemberRole.PRIMARY), None)
    replica_members = [m for m in members if m.role == ClusterMemberRole.REPLICA]

    if not replica_members:
        raise NoHealthyReplicaError(f"Cluster {cluster_id} has no replica to fail over to")

    candidates: list[tuple[ClusterMember, Node, int]] = []
    for member in replica_members:
        node = await db.get(Node, member.node_id)
        try:
            status = await get_member_replication_status(node)
        except AgentUnreachableError:
            continue
        if status.get("role") != "standby":
            continue
        candidates.append((member, node, status.get("lag_bytes") or 0))

    if not candidates:
        raise NoHealthyReplicaError(
            f"Cluster {cluster_id} has replicas registered, but none are currently "
            "reachable and healthy"
        )

    # Least lag first — the freshest replica loses the least data on promotion.
    candidates.sort(key=lambda c: c[2])
    chosen_member, chosen_node, chosen_lag = candidates[0]

    await call_agent(chosen_node, "POST", "/v1/replication/promote", timeout=30.0)

    chosen_member.role = ClusterMemberRole.PRIMARY
    chosen_member.promoted_at = utcnow()
    chosen_member.replication_lag_bytes = None

    old_primary_node_id = None
    if primary_member is not None:
        old_primary_node_id = primary_member.node_id
        # The old primary needs a fresh pg_basebackup before it could safely
        # rejoin as a replica — same day-0 provisioning boundary as adding any
        # other replica (cf. module docstring). Dropping it from tracking here
        # avoids the Orchestrator ever placing new load on a diverged node.
        await db.delete(primary_member)

    databases = (
        (
            await db.execute(
                select(Database).where(
                    Database.cluster_id == cluster_id, Database.status == DatabaseStatus.RUNNING
                )
            )
        )
        .scalars()
        .all()
    )
    for database in databases:
        database.connection_host = chosen_node.ip_address
        database.connection_port = chosen_node.postgres_port

    db.add(
        ClusterEvent(
            cluster_id=cluster_id,
            event_type="FAILOVER_COMPLETED",
            data={
                "automatic": automatic,
                "promoted_node_id": str(chosen_node.id),
                "promoted_member_id": str(chosen_member.id),
                "previous_primary_node_id": str(old_primary_node_id)
                if old_primary_node_id
                else None,
                "chosen_lag_bytes": chosen_lag,
                "databases_repointed": [str(d.id) for d in databases],
            },
        )
    )

    return {
        "promoted_node_id": str(chosen_node.id),
        "databases_repointed": len(databases),
    }
