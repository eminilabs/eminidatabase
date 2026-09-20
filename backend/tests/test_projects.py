from httpx import AsyncClient

from tests.conftest import register_and_login


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
