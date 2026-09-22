from httpx import AsyncClient

import app.worker as worker_module
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


async def _create_org(client: AsyncClient, headers: dict, slug: str = "acme") -> dict:
    resp = await client.post(
        "/api/v1/organizations", json={"name": "ACME", "slug": slug}, headers=headers
    )
    return resp.json()


async def test_create_and_list_projects(client: AsyncClient):
    headers = await register_and_login(client, "pmowner@example.com")
    org = await _create_org(client, headers, "acme-projects")

    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects",
        json={"name": "E-commerce", "slug": "ecommerce"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "ecommerce"

    listing = await client.get(
        f"/api/v1/organizations/{org['id']}/projects", headers=headers
    )
    assert len(listing.json()) == 1


async def test_project_slug_unique_per_organization(client: AsyncClient):
    headers = await register_and_login(client, "pmowner2@example.com")
    org = await _create_org(client, headers, "acme-projects-2")

    payload = {"name": "Shop", "slug": "shop"}
    first = await client.post(
        f"/api/v1/organizations/{org['id']}/projects", json=payload, headers=headers
    )
    second = await client.post(
        f"/api/v1/organizations/{org['id']}/projects", json=payload, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 409


async def test_member_from_other_org_cannot_list_projects(client: AsyncClient):
    owner_headers = await register_and_login(client, "pmowner3@example.com")
    org = await _create_org(client, owner_headers, "acme-projects-3")

    outsider_headers = await register_and_login(client, "outsider@example.com")
    resp = await client.get(
        f"/api/v1/organizations/{org['id']}/projects", headers=outsider_headers
    )
    assert resp.status_code == 404


async def test_readonly_cannot_create_project(client: AsyncClient):
    owner_headers = await register_and_login(client, "pmowner4@example.com")
    readonly_headers = await register_and_login(client, "readonlyuser@example.com")
    org = await _create_org(client, owner_headers, "acme-projects-4")

    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "readonlyuser@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects",
        json={"name": "Blocked", "slug": "blocked"},
        headers=readonly_headers,
    )
    assert resp.status_code == 403


async def test_delete_project_rejects_when_databases_remain(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "pmadmin1@example.com")
    owner_headers = await register_and_login(client, "pmowner5@example.com")
    org = await _create_org(client, owner_headers, "acme-projects-5")
    project = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/projects",
            json={"name": "Shop", "slug": "shop"},
            headers=owner_headers,
        )
    ).json()
    region = await create_region(client, admin_headers, "eu-proj-5")
    await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "main", "region_code": region["code"]},
        headers=owner_headers,
    )

    resp = await client.delete(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}", headers=owner_headers
    )
    assert resp.status_code == 409

    listing = await client.get(
        f"/api/v1/organizations/{org['id']}/projects", headers=owner_headers
    )
    assert project["id"] in [p["id"] for p in listing.json()]


async def test_delete_project_still_rejects_after_its_database_is_deleted(
    client: AsyncClient, monkeypatch
):
    """A soft-deleted database (status=DELETED) is a tombstone kept for
    billing/audit history — backups, credentials, query history, and
    usage_records (which feed real invoices) all still reference its row via
    plain FKs with no ondelete=CASCADE. Hard-deleting the project would either
    orphan those or (if the database row were cascade-removed too) silently
    destroy that history, so this must stay blocked even once the database
    itself is gone — a real 500 this test would have caught before the fix in
    app/api/v1/endpoints/projects.py that dropped the `status != DELETED`
    filter from the guard."""
    admin_headers = await register_platform_admin(client, "pmadmin7@example.com")
    owner_headers = await register_and_login(client, "pmowner7@example.com")
    org = await _create_org(client, owner_headers, "acme-projects-7")
    project = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/projects",
            json={"name": "Shop", "slug": "shop"},
            headers=owner_headers,
        )
    ).json()
    region = await create_region(client, admin_headers, "eu-proj-7")
    await register_and_activate_node(
        client, admin_headers, region["code"], hostname="vps-proj-7-a", ip_address="203.0.113.50"
    )

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "main", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(
        "app.services.orchestrator.call_agent",
        lambda node, method, path, *, json=None, params=None, timeout=30.0: _FakeAgentResponse(),
    )
    await worker_module.run_once()  # provisions -> RUNNING

    delete_resp = await client.delete(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}",
        headers=owner_headers,
    )
    assert delete_resp.status_code == 200
    await worker_module.run_once()  # deprovisions -> DELETED (row stays, soft delete)

    resp = await client.delete(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}", headers=owner_headers
    )
    assert resp.status_code == 409


class _FakeAgentResponse:
    def json(self) -> dict:
        return {"status": "ok"}


async def test_delete_empty_project_succeeds(client: AsyncClient):
    owner_headers = await register_and_login(client, "pmowner6@example.com")
    org = await _create_org(client, owner_headers, "acme-projects-6")
    project = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/projects",
            json={"name": "Empty", "slug": "empty"},
            headers=owner_headers,
        )
    ).json()

    resp = await client.delete(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}", headers=owner_headers
    )
    assert resp.status_code == 204

    listing = await client.get(
        f"/api/v1/organizations/{org['id']}/projects", headers=owner_headers
    )
    assert project["id"] not in [p["id"] for p in listing.json()]
