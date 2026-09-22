import uuid

from httpx import AsyncClient
from sqlalchemy import select

import app.worker as worker_module
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _FakeAgentResponse:
    def __init__(self, payload=None):
        self._payload = payload if payload is not None else {"status": "ok"}

    def json(self):
        return self._payload


async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
    return _FakeAgentResponse()


async def _create_running_database(
    client: AsyncClient, monkeypatch, suffix: str, **db_kwargs
) -> tuple[dict, dict, dict, str, dict]:
    admin_headers = await register_platform_admin(client, f"p7admin{suffix}@example.com")
    owner_headers = await register_and_login(client, f"p7owner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": f"acme-p7-{suffix}"},
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
    region = await create_region(client, admin_headers, f"eu-p7-{suffix}")
    await register_and_activate_node(
        client, admin_headers, region["code"], hostname=f"vps-p7-{suffix}-a",
        ip_address="203.0.113.40",
    )

    payload = {"name": "production", "region_code": region["code"], **db_kwargs}
    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json=payload,
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)
    await worker_module.run_once()

    return owner_headers, org, project, database_id, admin_headers


def _db_url(org: dict, project: dict, database_id: str) -> str:
    return f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}"


async def test_resize_updates_limits(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, _ = await _create_running_database(
        client, monkeypatch, "rz1"
    )

    calls = []

    async def _fake_resize_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        calls.append((path, json))
        return _FakeAgentResponse()

    monkeypatch.setattr("app.api.v1.endpoints.databases.call_agent", _fake_resize_call_agent)

    resp = await client.post(
        f"{_db_url(org, project, database_id)}/resize",
        json={"cpu_limit": 2, "ram_limit_mb": 2048, "storage_limit_gb": 20},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cpu_limit"] == 2
    assert body["ram_limit_mb"] == 2048
    assert body["storage_limit_gb"] == 20
    assert calls[0][0].endswith("/connection-limit")
    assert calls[0][1] == {"limit": 2 * 20}


async def test_suspend_then_resume_round_trip(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, _ = await _create_running_database(
        client, monkeypatch, "sr1"
    )

    suspend_resp = await client.post(
        f"{_db_url(org, project, database_id)}/suspend", headers=owner_headers
    )
    assert suspend_resp.status_code == 200
    assert suspend_resp.json()["database"]["status"] == "suspending"

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    await worker_module.run_once()

    get_resp = await client.get(_db_url(org, project, database_id), headers=owner_headers)
    assert get_resp.json()["status"] == "suspended"

    # Resize is only allowed while RUNNING — a suspended database should be
    # rejected the same way a still-provisioning one is.
    resize_resp = await client.post(
        f"{_db_url(org, project, database_id)}/resize",
        json={"cpu_limit": 2, "ram_limit_mb": 2048, "storage_limit_gb": 20},
        headers=owner_headers,
    )
    assert resize_resp.status_code == 409

    resume_resp = await client.post(
        f"{_db_url(org, project, database_id)}/resume", headers=owner_headers
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["database"]["status"] == "updating"

    await worker_module.run_once()

    get_resp = await client.get(_db_url(org, project, database_id), headers=owner_headers)
    assert get_resp.json()["status"] == "running"


async def test_cannot_suspend_a_database_that_is_not_running(client: AsyncClient, monkeypatch):
    admin_headers = await register_platform_admin(client, "p7admin9@example.com")
    owner_headers = await register_and_login(client, "p7owner9@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": "acme-p7-9"},
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
    region = await create_region(client, admin_headers, "eu-p7-9")
    # No node -> database stays CREATING.
    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    resp = await client.post(
        f"{_db_url(org, project, database_id)}/suspend", headers=owner_headers
    )
    assert resp.status_code == 409


async def test_readonly_cannot_suspend(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, _ = await _create_running_database(
        client, monkeypatch, "sr2"
    )
    readonly_headers = await register_and_login(client, "p7readonly9@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "p7readonly9@example.com", "role": "readonly"},
        headers=owner_headers,
    )
    resp = await client.post(
        f"{_db_url(org, project, database_id)}/suspend", headers=readonly_headers
    )
    assert resp.status_code == 403


async def test_resize_rejects_when_not_running(client: AsyncClient, monkeypatch):
    admin_headers = await register_platform_admin(client, "p7admin2@example.com")
    owner_headers = await register_and_login(client, "p7owner2@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": "acme-p7-2"},
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
    region = await create_region(client, admin_headers, "eu-p7-2")
    # No node -> database stays CREATING.
    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    resp = await client.post(
        f"{_db_url(org, project, database_id)}/resize",
        json={"cpu_limit": 2, "ram_limit_mb": 2048, "storage_limit_gb": 20},
        headers=owner_headers,
    )
    assert resp.status_code == 409


async def test_resize_rejects_when_it_does_not_fit_on_node(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, _ = await _create_running_database(
        client, monkeypatch, "rz3"
    )
    # Node was registered with the factory default cpu_total=4 — 32 (schema max)
    # can never fit regardless of what else is on the node.
    resp = await client.post(
        f"{_db_url(org, project, database_id)}/resize",
        json={"cpu_limit": 32, "ram_limit_mb": 2048, "storage_limit_gb": 20},
        headers=owner_headers,
    )
    assert resp.status_code == 409


async def test_readonly_cannot_resize(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, _ = await _create_running_database(
        client, monkeypatch, "rz4"
    )
    readonly_headers = await register_and_login(client, "p7readonly4@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "p7readonly4@example.com", "role": "readonly"},
        headers=owner_headers,
    )
    resp = await client.post(
        f"{_db_url(org, project, database_id)}/resize",
        json={"cpu_limit": 2, "ram_limit_mb": 2048, "storage_limit_gb": 20},
        headers=readonly_headers,
    )
    assert resp.status_code == 403


async def test_migrate_moves_database_to_target_node(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, admin_headers = await _create_running_database(
        client, monkeypatch, "mg1"
    )
    target_node = await register_and_activate_node(
        client, admin_headers, "eu-p7-mg1", hostname="vps-p7-mg1-b", ip_address="203.0.113.41"
    )

    migrate_resp = await client.post(
        f"/api/v1/databases/{database_id}/migrate",
        json={"target_node_id": target_node["node_id"]},
        headers=admin_headers,
    )
    assert migrate_resp.status_code == 202
    assert migrate_resp.json()["database"]["status"] == "migrating"

    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)
    await worker_module.run_once()

    db_resp = await client.get(_db_url(org, project, database_id), headers=owner_headers)
    body = db_resp.json()
    assert body["status"] == "running"
    assert body["connection_host"] == "203.0.113.41"


async def test_migrate_rejects_cross_region(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, admin_headers = await _create_running_database(
        client, monkeypatch, "mg2"
    )
    other_region = await create_region(client, admin_headers, "eu-p7-mg2-other")
    other_node = await register_and_activate_node(
        client, admin_headers, other_region["code"], hostname="vps-p7-mg2-other"
    )

    resp = await client.post(
        f"/api/v1/databases/{database_id}/migrate",
        json={"target_node_id": other_node["node_id"]},
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_migrate_rejects_unhealthy_target(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, admin_headers = await _create_running_database(
        client, monkeypatch, "mg3"
    )
    token = await client.post(
        "/api/v1/nodes/registration-tokens",
        json={"region_code": "eu-p7-mg3", "note": "unhealthy target"},
        headers=admin_headers,
    )
    from tests.factories import generate_csr_pem

    register_resp = await client.post(
        "/api/v1/nodes/register",
        headers={"Authorization": f"Bearer {token.json()['token']}"},
        json={
            "hostname": "vps-p7-mg3-unhealthy",
            "region_code": "eu-p7-mg3",
            "csr_pem": generate_csr_pem(),
            "cpu_total": 4,
            "ram_total_mb": 8192,
            "storage_total_gb": 100,
        },
    )
    # Deliberately never sending a heartbeat -> effective_status stays "offline".
    unhealthy_node_id = register_resp.json()["node_id"]

    resp = await client.post(
        f"/api/v1/databases/{database_id}/migrate",
        json={"target_node_id": unhealthy_node_id},
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_migrate_rejects_insufficient_capacity(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, admin_headers = await _create_running_database(
        client, monkeypatch, "mg4", cpu_limit=1, ram_limit_mb=1024, storage_limit_gb=10
    )
    tiny_node = await register_and_activate_node(
        client, admin_headers, "eu-p7-mg4", hostname="vps-p7-mg4-tiny",
        ip_address="203.0.113.42", cpu_total=1, ram_total_mb=512, storage_total_gb=5,
    )

    resp = await client.post(
        f"/api/v1/databases/{database_id}/migrate",
        json={"target_node_id": tiny_node["node_id"]},
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_non_admin_cannot_migrate(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, admin_headers = await _create_running_database(
        client, monkeypatch, "mg5"
    )
    target_node = await register_and_activate_node(
        client, admin_headers, "eu-p7-mg5", hostname="vps-p7-mg5-b"
    )
    resp = await client.post(
        f"/api/v1/databases/{database_id}/migrate",
        json={"target_node_id": target_node["node_id"]},
        headers=owner_headers,
    )
    assert resp.status_code == 403


async def test_migrate_terminal_failure_marks_database_failed(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id, admin_headers = await _create_running_database(
        client, monkeypatch, "mg6"
    )
    target_node = await register_and_activate_node(
        client, admin_headers, "eu-p7-mg6", hostname="vps-p7-mg6-b", ip_address="203.0.113.43"
    )
    await client.post(
        f"/api/v1/databases/{database_id}/migrate",
        json={"target_node_id": target_node["node_id"]},
        headers=admin_headers,
    )

    async def _always_fails(node, method, path, *, json=None, params=None, timeout=30.0):
        raise RuntimeError("agent exploded mid-migration")

    monkeypatch.setattr("app.services.orchestrator.call_agent", _always_fails)

    async with TestSessionLocal() as db:
        from app.models.job import Job

        job = (
            await db.execute(
                select(Job).where(
                    Job.resource_id == uuid.UUID(database_id),
                    Job.type == "migrate_database",
                )
            )
        ).scalar_one()
        job.max_attempts = 1
        await db.commit()

    await worker_module.run_once()

    db_resp = await client.get(_db_url(org, project, database_id), headers=owner_headers)
    assert db_resp.json()["status"] == "failed"
