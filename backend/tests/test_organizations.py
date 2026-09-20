from httpx import AsyncClient

from tests.conftest import register_and_login


async def test_create_organization_makes_creator_owner(client: AsyncClient):
    headers = await register_and_login(client, "owner@example.com")
    resp = await client.post(
        "/api/v1/organizations", json={"name": "ACME", "slug": "acme"}, headers=headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "acme"
    assert body["role"] == "owner"


async def test_duplicate_slug_rejected(client: AsyncClient):
    headers = await register_and_login(client, "owner2@example.com")
    payload = {"name": "ACME", "slug": "acme-dup"}
    first = await client.post("/api/v1/organizations", json=payload, headers=headers)
    second = await client.post("/api/v1/organizations", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 409


async def test_non_member_cannot_see_organization(client: AsyncClient):
    owner_headers = await register_and_login(client, "owner3@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "Private", "slug": "private-org"},
            headers=owner_headers,
        )
    ).json()

    stranger_headers = await register_and_login(client, "stranger@example.com")
    resp = await client.get(f"/api/v1/organizations/{org['id']}", headers=stranger_headers)
    assert resp.status_code == 404


async def test_owner_can_add_member_by_email(client: AsyncClient):
    owner_headers = await register_and_login(client, "owner4@example.com")
    await register_and_login(client, "newmember@example.com")

    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "Team", "slug": "team-1"},
            headers=owner_headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "newmember@example.com", "role": "developer"},
        headers=owner_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "developer"

    members = await client.get(
        f"/api/v1/organizations/{org['id']}/members", headers=owner_headers
    )
    assert len(members.json()) == 2


async def test_readonly_member_cannot_add_members(client: AsyncClient):
    owner_headers = await register_and_login(client, "owner5@example.com")
    readonly_headers = await register_and_login(client, "readonly@example.com")
    await register_and_login(client, "third@example.com")

    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "Team2", "slug": "team-2"},
            headers=owner_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "readonly@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "third@example.com", "role": "developer"},
        headers=readonly_headers,
    )
    assert resp.status_code == 403


async def test_cannot_remove_last_owner(client: AsyncClient):
    owner_headers = await register_and_login(client, "soleowner@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "Solo", "slug": "solo-org"},
            headers=owner_headers,
        )
    ).json()

    me = (await client.get("/api/v1/auth/me", headers=owner_headers)).json()
    resp = await client.delete(
        f"/api/v1/organizations/{org['id']}/members/{me['id']}", headers=owner_headers
    )
    assert resp.status_code == 400
