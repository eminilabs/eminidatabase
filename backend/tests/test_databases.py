import uuid

from httpx import AsyncClient
from sqlalchemy import select

import app.worker as worker_module
from app.models.job import Job
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _FakeAgentResponse:
    def json(self):
        return {"status": "ok"}

    text = "ok"


async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
    return _FakeAgentResponse()


async def _run_worker_tick(monkeypatch) -> bool:
    """Runs exactly one worker iteration against the test DB, with the mTLS call
    to the (nonexistent, in this test) agent replaced by a no-op success."""
    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)
    return await worker_module.run_once()


async def _setup_org_project_node(
    client: AsyncClient, admin_headers: dict, suffix: str
) -> tuple[dict, dict, dict, dict]:
    owner_headers = await register_and_login(client, f"dbowner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": f"acme-db-{suffix}"},
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
    region = await create_region(client, admin_headers, f"eu-db-{suffix}")
    await register_and_activate_node(
        client, admin_headers, region["code"], hostname=f"vps-db-{suffix}"
    )
    return owner_headers, org, project, region


async def test_create_database_end_to_end(client: AsyncClient, monkeypatch):
    admin_headers = await register_platform_admin(client, "dbadmin1@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "1"
    )

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    assert create_resp.status_code == 202
    body = create_resp.json()
    assert body["database"]["status"] == "creating"
    assert body["database"]["cluster_id"] is None
    database_id = body["database"]["id"]
    job_id = body["job_id"]

    processed = await _run_worker_tick(monkeypatch)
    assert processed is True

    job_resp = await client.get(f"/api/v1/jobs/{job_id}", headers=owner_headers)
    assert job_resp.status_code == 200
    assert job_resp.json()["status"] == "succeeded"

    db_url = f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}"
    db_body = (await client.get(db_url, headers=owner_headers)).json()
    assert db_body["status"] == "running"
    assert db_body["cluster_id"] is not None
    assert db_body["connection_host"] is not None
    assert db_body["connection_port"] is not None

    conn_resp = await client.get(f"{db_url}/connection", headers=owner_headers)
    assert conn_resp.status_code == 200
    conn = conn_resp.json()
    assert conn["connection_string"].startswith("postgresql://")
    assert conn["password"] in conn["connection_string"]
    assert conn["database"].startswith("db_")


async def test_duplicate_database_name_in_project_rejected(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "dbadmin2@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "2"
    )

    payload = {"name": "production", "region_code": region["code"]}
    first = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json=payload,
        headers=owner_headers,
    )
    second = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json=payload,
        headers=owner_headers,
    )
    assert first.status_code == 202
    assert second.status_code == 409


async def test_readonly_member_cannot_create_database(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "dbadmin3@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "3"
    )
    readonly_headers = await register_and_login(client, "dbreadonly3@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "dbreadonly3@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "blocked", "region_code": region["code"]},
        headers=readonly_headers,
    )
    assert resp.status_code == 403


async def test_readonly_member_cannot_fetch_connection_secrets(
    client: AsyncClient, monkeypatch
):
    admin_headers = await register_platform_admin(client, "dbadmin5@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "5"
    )
    readonly_headers = await register_and_login(client, "dbreadonly5@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "dbreadonly5@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]
    await _run_worker_tick(monkeypatch)

    base = f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}"
    # Readonly can see the database exists...
    assert (await client.get(base, headers=readonly_headers)).status_code == 200
    # ...but not its live password.
    assert (await client.get(f"{base}/connection", headers=readonly_headers)).status_code == 403
    assert (await client.get(f"{base}/connection", headers=owner_headers)).status_code == 200


async def test_create_database_without_capacity_marks_failed(
    client: AsyncClient, monkeypatch
):
    admin_headers = await register_platform_admin(client, "dbadmin4@example.com")
    owner_headers = await register_and_login(client, "dbowner4@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": "acme-db-4"},
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
    # A region with no node at all -> the job can never place the database.
    region = await create_region(client, admin_headers, "eu-db-4-empty")

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)

    # Force immediate terminal failure instead of waiting through retry backoff.
    async with TestSessionLocal() as db:
        job = (
            await db.execute(select(Job).where(Job.resource_id == uuid.UUID(database_id)))
        ).scalar_one()
        job.max_attempts = 1
        await db.commit()

    await worker_module.run_once()

    db_url = f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}"
    db_body = (await client.get(db_url, headers=owner_headers)).json()
    assert db_body["status"] == "failed"
