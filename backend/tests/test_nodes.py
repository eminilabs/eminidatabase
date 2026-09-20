from httpx import AsyncClient

from tests.conftest import register_and_login, register_platform_admin


def _generate_csr_pem(common_name: str = "unbootstrapped-node") -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


async def _create_region(client: AsyncClient, admin_headers: dict, code: str = "eu-west") -> dict:
    resp = await client.post(
        "/api/v1/regions", json={"code": code, "name": "Europe West"}, headers=admin_headers
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_bootstrap_token(
    client: AsyncClient, admin_headers: dict, region_code: str
) -> str:
    resp = await client.post(
        "/api/v1/nodes/registration-tokens",
        json={"region_code": region_code, "note": "test node"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    return resp.json()["token"]


async def test_only_platform_admin_can_create_region(client: AsyncClient):
    regular_headers = await register_and_login(client, "regular@example.com")
    resp = await client.post(
        "/api/v1/regions", json={"code": "eu-west", "name": "Europe"}, headers=regular_headers
    )
    assert resp.status_code == 403


async def test_any_authenticated_user_can_list_regions(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "admin1@example.com")
    await _create_region(client, admin_headers, "eu-west-1")

    regular_headers = await register_and_login(client, "regular2@example.com")
    resp = await client.get("/api/v1/regions", headers=regular_headers)
    assert resp.status_code == 200
    assert any(r["code"] == "eu-west-1" for r in resp.json())


async def test_node_registration_flow(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "admin2@example.com")
    region = await _create_region(client, admin_headers, "eu-west-2")
    token = await _create_bootstrap_token(client, admin_headers, region["code"])

    resp = await client.post(
        "/api/v1/nodes/register",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "hostname": "vps-01.example.net",
            "region_code": region["code"],
            "csr_pem": _generate_csr_pem(),
            "ip_address": "203.0.113.10",
            "cpu_total": 4,
            "ram_total_mb": 8192,
            "storage_total_gb": 100,
            "agent_version": "0.1.0",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "node_id" in body
    assert body["certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")
    assert body["ca_certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")

    node = (
        await client.get(f"/api/v1/nodes/{body['node_id']}", headers=admin_headers)
    ).json()
    assert node["hostname"] == "vps-01.example.net"
    assert node["effective_status"] == "offline"  # no heartbeat sent yet


async def test_bootstrap_token_cannot_be_reused(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "admin3@example.com")
    region = await _create_region(client, admin_headers, "eu-west-3")
    token = await _create_bootstrap_token(client, admin_headers, region["code"])

    payload = {
        "hostname": "vps-02.example.net",
        "region_code": region["code"],
        "csr_pem": _generate_csr_pem(),
        "cpu_total": 2,
        "ram_total_mb": 4096,
        "storage_total_gb": 50,
    }
    first = await client.post(
        "/api/v1/nodes/register", headers={"Authorization": f"Bearer {token}"}, json=payload
    )
    second = await client.post(
        "/api/v1/nodes/register",
        headers={"Authorization": f"Bearer {token}"},
        json={**payload, "hostname": "vps-03.example.net", "csr_pem": _generate_csr_pem()},
    )
    assert first.status_code == 201
    assert second.status_code == 401


async def test_heartbeat_then_node_reports_active(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "admin4@example.com")
    region = await _create_region(client, admin_headers, "eu-west-4")
    token = await _create_bootstrap_token(client, admin_headers, region["code"])

    register_resp = await client.post(
        "/api/v1/nodes/register",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "hostname": "vps-04.example.net",
            "region_code": region["code"],
            "csr_pem": _generate_csr_pem(),
            "cpu_total": 2,
            "ram_total_mb": 4096,
            "storage_total_gb": 50,
        },
    )
    node_id = register_resp.json()["node_id"]
    node_secret = register_resp.json()["node_secret"]

    heartbeat_resp = await client.post(
        f"/api/v1/nodes/{node_id}/heartbeat",
        headers={"Authorization": f"Bearer {node_secret}"},
        json={"cpu_used": 0.5, "ram_used_mb": 1024, "storage_used_gb": 10},
    )
    assert heartbeat_resp.status_code == 204

    node = (await client.get(f"/api/v1/nodes/{node_id}", headers=admin_headers)).json()
    assert node["effective_status"] == "active"
    assert node["cpu_used"] == 0.5
    assert node["last_heartbeat_at"] is not None


async def test_heartbeat_rejects_wrong_secret(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "admin5@example.com")
    region = await _create_region(client, admin_headers, "eu-west-5")
    token = await _create_bootstrap_token(client, admin_headers, region["code"])

    register_resp = await client.post(
        "/api/v1/nodes/register",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "hostname": "vps-05.example.net",
            "region_code": region["code"],
            "csr_pem": _generate_csr_pem(),
            "cpu_total": 2,
            "ram_total_mb": 4096,
            "storage_total_gb": 50,
        },
    )
    node_id = register_resp.json()["node_id"]

    resp = await client.post(
        f"/api/v1/nodes/{node_id}/heartbeat",
        headers={"Authorization": "Bearer wrong-secret"},
        json={},
    )
    assert resp.status_code == 401


async def test_health_check_without_known_ip_reports_unreachable(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "admin6@example.com")
    region = await _create_region(client, admin_headers, "eu-west-6")
    token = await _create_bootstrap_token(client, admin_headers, region["code"])

    register_resp = await client.post(
        "/api/v1/nodes/register",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "hostname": "vps-06.example.net",
            "region_code": region["code"],
            "csr_pem": _generate_csr_pem(),
            "cpu_total": 2,
            "ram_total_mb": 4096,
            "storage_total_gb": 50,
        },
    )
    node_id = register_resp.json()["node_id"]

    resp = await client.post(f"/api/v1/nodes/{node_id}/health-check", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is False
