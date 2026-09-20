"""Database Orchestrator placement — decides which node/cluster hosts a new
Database. Cf. docs/architecture/03-database-orchestrator-et-agent.md §"Algorithme de
placement" and §7 of the cahier des charges.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster, ClusterStatus
from app.models.cluster_member import ClusterMember
from app.models.database import Database, DatabaseStatus, IsolationLevel
from app.models.node import Node
from app.models.region import Region
from app.services.node_health import is_eligible_for_placement


class NoCapacityError(Exception):
    pass


@dataclass
class PlacementDecision:
    node: Node
    existing_cluster: Cluster | None  # None means: create a new cluster


def _score(
    node: Node, allocated_cpu: int, allocated_ram_mb: int, allocated_storage_gb: int
) -> float:
    """Higher is better. Weighted free-capacity fractions, explicit and configurable
    (cahier des charges §7 — not a black box)."""
    cpu_free = max(0.0, (node.cpu_total - allocated_cpu) / node.cpu_total)
    ram_free = max(0.0, (node.ram_total_mb - allocated_ram_mb) / node.ram_total_mb)
    storage_free = max(0.0, (node.storage_total_gb - allocated_storage_gb) / node.storage_total_gb)
    return cpu_free + ram_free + storage_free


async def allocated_resources(
    db: AsyncSession, node_id, *, exclude_database_id=None
) -> tuple[int, int, int]:
    """Sum of resource limits of every non-deleted Database hosted (via its
    Cluster's ClusterMembers) on this node. `exclude_database_id` lets a resize
    check a database's fit against everyone *else's* usage, not counting its own
    current (pre-resize) allocation twice."""
    conditions = [
        ClusterMember.node_id == node_id,
        Database.status != DatabaseStatus.DELETED,
    ]
    if exclude_database_id is not None:
        conditions.append(Database.id != exclude_database_id)

    rows = (
        await db.execute(
            select(Database.cpu_limit, Database.ram_limit_mb, Database.storage_limit_gb)
            .join(Cluster, Cluster.id == Database.cluster_id)
            .join(ClusterMember, ClusterMember.cluster_id == Cluster.id)
            .where(*conditions)
        )
    ).all()
    cpu = sum(r[0] for r in rows)
    ram = sum(r[1] for r in rows)
    storage = sum(r[2] for r in rows)
    return cpu, ram, storage


async def find_shared_cluster_on_node(db: AsyncSession, node_id) -> Cluster | None:
    return (
        await db.execute(
            select(Cluster)
            .join(ClusterMember, ClusterMember.cluster_id == Cluster.id)
            .where(
                ClusterMember.node_id == node_id,
                Cluster.shared.is_(True),
                Cluster.status == ClusterStatus.ACTIVE,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def fits_on_node(
    db: AsyncSession,
    node: Node,
    *,
    cpu_limit: int,
    ram_limit_mb: int,
    storage_limit_gb: int,
    exclude_database_id=None,
) -> bool:
    cpu, ram, storage = await allocated_resources(
        db, node.id, exclude_database_id=exclude_database_id
    )
    return (
        cpu + cpu_limit <= node.cpu_total
        and ram + ram_limit_mb <= node.ram_total_mb
        and storage + storage_limit_gb <= node.storage_total_gb
    )


async def select_node_and_cluster(
    db: AsyncSession,
    *,
    region_code: str,
    isolation_level: IsolationLevel,
    cpu_limit: int,
    ram_limit_mb: int,
    storage_limit_gb: int,
) -> PlacementDecision:
    region = (
        await db.execute(select(Region).where(Region.code == region_code, Region.active.is_(True)))
    ).scalar_one_or_none()
    if region is None:
        raise ValueError(f"Unknown or inactive region: {region_code}")

    nodes = (
        (await db.execute(select(Node).where(Node.region_id == region.id))).scalars().all()
    )
    eligible = [n for n in nodes if is_eligible_for_placement(n)]
    if not eligible:
        raise NoCapacityError(f"No active node available in region {region_code}")

    scored: list[tuple[float, Node, int, int, int]] = []
    for node in eligible:
        cpu, ram, storage = await allocated_resources(db, node.id)
        fits = (
            cpu + cpu_limit <= node.cpu_total
            and ram + ram_limit_mb <= node.ram_total_mb
            and storage + storage_limit_gb <= node.storage_total_gb
        )
        if not fits:
            continue
        scored.append((_score(node, cpu, ram, storage), node, cpu, ram, storage))

    if not scored:
        raise NoCapacityError(f"No node in region {region_code} has enough free capacity")

    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best_node, _, _, _ = scored[0]

    if isolation_level == IsolationLevel.DEDICATED:
        return PlacementDecision(node=best_node, existing_cluster=None)

    existing_cluster = await find_shared_cluster_on_node(db, best_node.id)
    return PlacementDecision(node=best_node, existing_cluster=existing_cluster)
