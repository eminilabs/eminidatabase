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
