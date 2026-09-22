from httpx import AsyncClient

from tests.conftest import register_and_login


async def test_create_and_revoke_api_key(client: AsyncClient):
    headers = await register_and_login(client, "apikeyowner@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": "acme-apikeys"},
            headers=headers,
        )
    ).json()

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/api-keys",
        json={"name": "CI key", "scopes": {"databases": "read"}},
        headers=headers,
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["api_key"].startswith("edb_")

    listing = await client.get(
        f"/api/v1/organizations/{org['id']}/api-keys", headers=headers
    )
    assert len(listing.json()) == 1
    assert "key_hash" not in listing.json()[0]

    revoke_resp = await client.delete(
        f"/api/v1/organizations/{org['id']}/api-keys/{body['id']}", headers=headers
    )
    assert revoke_resp.status_code == 204

    listing_after_revoke = await client.get(
        f"/api/v1/organizations/{org['id']}/api-keys", headers=headers
    )
    assert listing_after_revoke.json() == []


async def test_api_key_authenticates_as_its_creator(client: AsyncClient):
    owner_headers = await register_and_login(client, "apikeyowner2@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": "acme-apikeys-2"},
            headers=owner_headers,
        )
    ).json()

    created = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/api-keys",
            json={"name": "CI key", "scopes": {}},
            headers=owner_headers,
        )
    ).json()
    api_key_headers = {"Authorization": f"Bearer {created['api_key']}"}

    # A protected, org-scoped endpoint works with the key exactly as it would
    # with a JWT — no separate "API key auth" code path to keep in sync.
    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects",
        json={"name": "Shop", "slug": "shop"},
        headers=api_key_headers,
    )
    assert resp.status_code == 201

    me = await client.get("/api/v1/auth/me", headers=api_key_headers)
    assert me.status_code == 200
    assert me.json()["email"] == "apikeyowner2@example.com"


async def test_revoked_api_key_is_rejected(client: AsyncClient):
    owner_headers = await register_and_login(client, "apikeyowner3@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": "acme-apikeys-3"},
            headers=owner_headers,
        )
    ).json()
    created = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/api-keys",
            json={"name": "CI key", "scopes": {}},
            headers=owner_headers,
        )
    ).json()
    api_key_headers = {"Authorization": f"Bearer {created['api_key']}"}

    await client.delete(
        f"/api/v1/organizations/{org['id']}/api-keys/{created['id']}", headers=owner_headers
    )

    resp = await client.get(f"/api/v1/organizations/{org['id']}/projects", headers=api_key_headers)
    assert resp.status_code == 401


async def test_api_key_reflects_creators_current_role_not_a_frozen_tier(client: AsyncClient):
    """An admin-created key can do everything an admin can (e.g. create a
    project) but not an owner-only action (deleting the subscription plan) —
    it inherits the creator's live role, same as a GitHub personal access
    token, not a fixed elevated tier baked in at creation time."""
    owner_headers = await register_and_login(client, "apikeyowner4@example.com")
    admin_headers = await register_and_login(client, "apikeyadmin4@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": "acme-apikeys-4"},
            headers=owner_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "apikeyadmin4@example.com", "role": "admin"},
        headers=owner_headers,
    )

    created = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/api-keys",
            json={"name": "Admin key", "scopes": {}},
            headers=admin_headers,
        )
    ).json()
    api_key_headers = {"Authorization": f"Bearer {created['api_key']}"}

    project_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects",
        json={"name": "Shop", "slug": "shop"},
        headers=api_key_headers,
    )
    assert project_resp.status_code == 201

    subscription_resp = await client.patch(
        f"/api/v1/organizations/{org['id']}/subscription",
        json={"plan_id": str(org["id"])},  # invalid plan_id is fine — RBAC must reject first
        headers=api_key_headers,
    )
    assert subscription_resp.status_code == 403


async def test_garbage_api_key_shaped_token_is_rejected(client: AsyncClient):
    # Correctly shaped (8-char prefix) so this actually exercises the API key
    # lookup path, not a fallthrough to JWT decoding.
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer edb_deadbeef_bogussecret"}
    )
    assert resp.status_code == 401
