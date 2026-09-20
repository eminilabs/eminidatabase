import uuid

from httpx import AsyncClient
from sqlalchemy import select

import app.scheduler as scheduler_module
import app.worker as worker_module
from app.models.cluster import Cluster, ClusterStatus, ClusterTopology
from app.models.cluster_event import ClusterEvent
from app.models.cluster_member import ClusterMember, ClusterMemberRole
from app.services import ha_orchestrator as ha_module
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _FakeAgentResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


async def _create_running_database_with_cluster(
    client: AsyncClient, monkeypatch, suffix: str
) -> tuple[dict, dict, dict, str, str, dict]:
    """Returns (owner_headers, org, project, database_id, cluster_id, primary_node)."""

    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"status": "ok"})

    admin_headers = await register_platform_admin(client, f"p6admin{suffix}@example.com")
    owner_headers = await register_and_login(client, f"p6owner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": f"acme-p6-{suffix}"},
            headers=owner_headers,
        )
    ).json()
    project = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/projects",
            json={"name": "Shop", "slug": "shop"},
            headers=owner_headers,
        )
    ).json()
    region = await create_region(client, admin_headers, f"eu-p6-{suffix}")
    primary_node = await register_and_activate_node(
        client, admin_headers, region["code"], hostname=f"vps-p6-{suffix}-primary",
        ip_address="203.0.113.10",
    )

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)
    await worker_module.run_once()

    db_resp = await client.get(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}",
        headers=owner_headers,
    )
    cluster_id = db_resp.json()["cluster_id"]

    return owner_headers, org, project, database_id, cluster_id, admin_headers, primary_node


async def test_attach_replica_requires_standby_report(client: AsyncClient, monkeypatch):
    _, _, _, _, cluster_id, admin_headers, _ = await _create_running_database_with_cluster(
        client, monkeypatch, "ha1"
    )
    admin_headers = await register_platform_admin(client, "p6admin1b@example.com")
    replica_node = await register_and_activate_node(
        client, admin_headers, "eu-p6-ha1", hostname="vps-p6-ha1-replica", ip_address="203.0.113.20"
    )

    async def _fake_status(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"role": "primary"})  # not a standby

    monkeypatch.setattr("app.services.ha_orchestrator.call_agent", _fake_status)

    resp = await client.post(
        f"/api/v1/clusters/{cluster_id}/replicas",
        json={"node_id": replica_node["node_id"]},
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_attach_replica_success(client: AsyncClient, monkeypatch):
    _, _, _, _, cluster_id, admin_headers, _ = await _create_running_database_with_cluster(
        client, monkeypatch, "ha2"
    )
    replica_node = await register_and_activate_node(
        client, admin_headers, "eu-p6-ha2", hostname="vps-p6-ha2-replica", ip_address="203.0.113.21"
    )

    async def _fake_status(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"role": "standby", "lag_bytes": 128})

    monkeypatch.setattr("app.services.ha_orchestrator.call_agent", _fake_status)

    resp = await client.post(
        f"/api/v1/clusters/{cluster_id}/replicas",
        json={"node_id": replica_node["node_id"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "replica"
    assert resp.json()["replication_lag_bytes"] == 128

    cluster_resp = await client.get(f"/api/v1/clusters/{cluster_id}", headers=admin_headers)
    roles = {m["role"] for m in cluster_resp.json()["members"]}
    assert roles == {"primary", "replica"}


async def test_non_admin_cannot_manage_clusters(client: AsyncClient, monkeypatch):
    owner_headers, _, _, _, cluster_id, _, _ = await _create_running_database_with_cluster(
        client, monkeypatch, "ha3"
    )
    resp = await client.get(f"/api/v1/clusters/{cluster_id}", headers=owner_headers)
    assert resp.status_code == 403


async def _attach_mocked_replica(
    client, monkeypatch, cluster_id, admin_headers, region_code, suffix
):
    replica_node = await register_and_activate_node(
        client, admin_headers, region_code, hostname=f"vps-p6-{suffix}-replica",
        ip_address="203.0.113.30",
    )

    async def _fake_status(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"role": "standby", "lag_bytes": 0})

    monkeypatch.setattr("app.services.ha_orchestrator.call_agent", _fake_status)
    resp = await client.post(
        f"/api/v1/clusters/{cluster_id}/replicas",
        json={"node_id": replica_node["node_id"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    return replica_node


async def test_manual_failover_promotes_replica_and_repoints_database(
    client: AsyncClient, monkeypatch
):
    (owner_headers, org, project, database_id, cluster_id, admin_headers, primary_node) = (
        await _create_running_database_with_cluster(client, monkeypatch, "ha4")
    )
    replica_node = await _attach_mocked_replica(
        client, monkeypatch, cluster_id, admin_headers, "eu-p6-ha4", "ha4"
    )

    promote_calls = []

    async def _fake_ha_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        if path == "/v1/replication/promote":
            promote_calls.append(node.id)
            return _FakeAgentResponse({"status": "promoted"})
        return _FakeAgentResponse({"role": "standby", "lag_bytes": 0})

    monkeypatch.setattr("app.services.ha_orchestrator.call_agent", _fake_ha_call_agent)

    resp = await client.post(f"/api/v1/clusters/{cluster_id}/failover", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["promoted_node_id"] == replica_node["node_id"]
    assert body["databases_repointed"] == 1
    assert len(promote_calls) == 1

    db_resp = await client.get(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}",
        headers=owner_headers,
    )
    assert db_resp.json()["connection_host"] == "203.0.113.30"

    cluster_resp = await client.get(f"/api/v1/clusters/{cluster_id}", headers=admin_headers)
    members = cluster_resp.json()["members"]
    assert len(members) == 1  # old primary dropped from tracking
    assert members[0]["role"] == "primary"
    assert members[0]["node_id"] == replica_node["node_id"]

    async with TestSessionLocal() as db:
        events = (
            await db.execute(
                select(ClusterEvent).where(ClusterEvent.cluster_id == uuid.UUID(cluster_id))
            )
        ).scalars().all()
    assert any(e.event_type == "FAILOVER_COMPLETED" for e in events)


async def test_failover_without_replica_returns_409(client: AsyncClient, monkeypatch):
    _, _, _, _, cluster_id, admin_headers, _ = await _create_running_database_with_cluster(
        client, monkeypatch, "ha5"
    )
    resp = await client.post(f"/api/v1/clusters/{cluster_id}/failover", headers=admin_headers)
    assert resp.status_code == 409


async def test_scheduler_triggers_automatic_failover_on_dead_primary(
    client: AsyncClient, monkeypatch
):
    (_, _, _, _, cluster_id, admin_headers, primary_node) = (
        await _create_running_database_with_cluster(client, monkeypatch, "ha6")
    )
    replica_node = await _attach_mocked_replica(
        client, monkeypatch, cluster_id, admin_headers, "eu-p6-ha6", "ha6"
    )

    # Simulate the primary's node dying: force its cluster topology to HA and
    # wipe its heartbeat so app.services.node_health reports it offline.
    async with TestSessionLocal() as db:
        cluster = await db.get(Cluster, uuid.UUID(cluster_id))
        cluster.topology = ClusterTopology.PRIMARY_REPLICA
        cluster.status = ClusterStatus.ACTIVE
        from app.models.node import Node

        node = await db.get(Node, uuid.UUID(primary_node["node_id"]))
        node.last_heartbeat_at = None
        await db.commit()

    async def _fake_ha_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        if path == "/v1/replication/promote":
            return _FakeAgentResponse({"status": "promoted"})
        return _FakeAgentResponse({"role": "standby", "lag_bytes": 0})

    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(ha_module, "call_agent", _fake_ha_call_agent)

    failovers = await scheduler_module.check_and_failover_unhealthy_clusters()
    assert failovers == 1

    async with TestSessionLocal() as db:
        members = (
            await db.execute(
                select(ClusterMember).where(ClusterMember.cluster_id == uuid.UUID(cluster_id))
            )
        ).scalars().all()
    assert len(members) == 1
    assert members[0].role == ClusterMemberRole.PRIMARY
    assert str(members[0].node_id) == replica_node["node_id"]


async def test_scheduler_does_not_failover_healthy_primary(client: AsyncClient, monkeypatch):
    (_, _, _, database_id, cluster_id, admin_headers, primary_node) = (
        await _create_running_database_with_cluster(client, monkeypatch, "ha7")
    )
    await _attach_mocked_replica(client, monkeypatch, cluster_id, admin_headers, "eu-p6-ha7", "ha7")

    async with TestSessionLocal() as db:
        cluster = await db.get(Cluster, uuid.UUID(cluster_id))
        cluster.topology = ClusterTopology.PRIMARY_REPLICA
        await db.commit()

    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", TestSessionLocal)
    # Primary still has a fresh heartbeat from _create_running_database_with_cluster
    # -> is_eligible_for_placement is True -> no failover should be attempted.
    failovers = await scheduler_module.check_and_failover_unhealthy_clusters()
    assert failovers == 0
