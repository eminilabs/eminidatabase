import uuid

import pytest
from httpx import AsyncClient

from app.core.timeutil import utcnow
from app.models.cluster import Cluster, ClusterStatus, ClusterTopology
from app.models.cluster_member import ClusterMember, ClusterMemberRole
from app.models.database import Database, DatabaseStatus, IsolationLevel
from app.models.node import Node, NodeStatus
from app.models.region import Region
from app.services.placement import NoCapacityError, select_node_and_cluster
from tests.conftest import TestSessionLocal


async def test_select_node_prefers_least_loaded(client: AsyncClient):
    # `client` triggers the autouse schema-creation fixture before we touch the DB.
    async with TestSessionLocal() as db:
        region = Region(code="eu-place-1", name="Placement Test")
        db.add(region)
        await db.flush()

        busy_node = Node(
            region_id=region.id,
            hostname="busy",
            ip_address="10.0.0.1",
            cpu_total=4,
            ram_total_mb=8192,
            storage_total_gb=100,
            node_secret_hash="x",
            status=NodeStatus.ACTIVE,
            last_heartbeat_at=utcnow(),
        )
        idle_node = Node(
            region_id=region.id,
            hostname="idle",
            ip_address="10.0.0.2",
            cpu_total=4,
            ram_total_mb=8192,
            storage_total_gb=100,
            node_secret_hash="x",
            status=NodeStatus.ACTIVE,
            last_heartbeat_at=utcnow(),
        )
        db.add_all([busy_node, idle_node])
        await db.flush()

        cluster = Cluster(
            region_id=region.id,
            topology=ClusterTopology.SINGLE,
            shared=True,
            status=ClusterStatus.ACTIVE,
        )
        db.add(cluster)
        await db.flush()
        db.add(
            ClusterMember(
                cluster_id=cluster.id, node_id=busy_node.id, role=ClusterMemberRole.PRIMARY
            )
        )
        db.add(
            Database(
                project_id=uuid.uuid4(),
                region_id=region.id,
                cluster_id=cluster.id,
                name="existing",
                physical_name=f"db_{uuid.uuid4().hex[:20]}",
                isolation_level=IsolationLevel.SHARED,
                status=DatabaseStatus.RUNNING,
                cpu_limit=3,
                ram_limit_mb=6000,
                storage_limit_gb=80,
            )
        )
        await db.commit()

        decision = await select_node_and_cluster(
            db,
            region_code="eu-place-1",
            isolation_level=IsolationLevel.SHARED,
            cpu_limit=1,
            ram_limit_mb=512,
            storage_limit_gb=5,
        )
        assert decision.node.id == idle_node.id


async def test_no_capacity_raises(client: AsyncClient):
    async with TestSessionLocal() as db:
        region = Region(code="eu-place-2", name="Full Region")
        db.add(region)
        await db.flush()
        node = Node(
            region_id=region.id,
            hostname="full",
            ip_address="10.0.0.3",
            cpu_total=1,
            ram_total_mb=1024,
            storage_total_gb=10,
            node_secret_hash="x",
            status=NodeStatus.ACTIVE,
            last_heartbeat_at=utcnow(),
        )
        db.add(node)
        await db.commit()

        with pytest.raises(NoCapacityError):
            await select_node_and_cluster(
                db,
                region_code="eu-place-2",
                isolation_level=IsolationLevel.SHARED,
                cpu_limit=100,
                ram_limit_mb=100,
                storage_limit_gb=100,
            )


async def test_offline_node_is_excluded_from_placement(client: AsyncClient):
    async with TestSessionLocal() as db:
        region = Region(code="eu-place-3", name="Stale Heartbeat")
        db.add(region)
        await db.flush()
        # No last_heartbeat_at at all -> effective_status "offline" (cf.
        # app/services/node_health.py), so it must never be selected.
        node = Node(
            region_id=region.id,
            hostname="never-heartbeat",
            ip_address="10.0.0.4",
            cpu_total=8,
            ram_total_mb=16384,
            storage_total_gb=500,
            node_secret_hash="x",
            status=NodeStatus.ACTIVE,
        )
        db.add(node)
        await db.commit()

        with pytest.raises(NoCapacityError):
            await select_node_and_cluster(
                db,
                region_code="eu-place-3",
                isolation_level=IsolationLevel.SHARED,
                cpu_limit=1,
                ram_limit_mb=512,
                storage_limit_gb=5,
            )
