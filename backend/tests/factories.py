"""Shared test setup helpers for anything that needs a registered, active node —
used by test_nodes.py and the Phase 3 orchestrator/database tests."""

from __future__ import annotations

from httpx import AsyncClient


def generate_csr_pem(common_name: str = "unbootstrapped-node") -> str:
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


async def create_region(client: AsyncClient, admin_headers: dict, code: str = "eu-west") -> dict:
    resp = await client.post(
        "/api/v1/regions", json={"code": code, "name": "Europe West"}, headers=admin_headers
    )
    assert resp.status_code == 201
    return resp.json()


async def create_bootstrap_token(
    client: AsyncClient, admin_headers: dict, region_code: str
) -> str:
    resp = await client.post(
        "/api/v1/nodes/registration-tokens",
        json={"region_code": region_code, "note": "test node"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    return resp.json()["token"]


async def register_and_activate_node(
    client: AsyncClient,
    admin_headers: dict,
    region_code: str,
    hostname: str,
    ip_address: str = "203.0.113.10",
    cpu_total: int = 4,
    ram_total_mb: int = 8192,
    storage_total_gb: int = 100,
) -> dict:
    """Registers a node and immediately sends a heartbeat so it reads as 'active'
    (effective_status depends on heartbeat freshness — cf. app/services/node_health.py)."""
    token = await create_bootstrap_token(client, admin_headers, region_code)
    register_resp = await client.post(
        "/api/v1/nodes/register",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "hostname": hostname,
            "region_code": region_code,
            "csr_pem": generate_csr_pem(hostname),
            "ip_address": ip_address,
            "cpu_total": cpu_total,
            "ram_total_mb": ram_total_mb,
            "storage_total_gb": storage_total_gb,
            "agent_version": "0.1.0",
        },
    )
    assert register_resp.status_code == 201
    body = register_resp.json()

    heartbeat_resp = await client.post(
        f"/api/v1/nodes/{body['node_id']}/heartbeat",
        headers={"Authorization": f"Bearer {body['node_secret']}"},
        json={"cpu_used": 0.1, "ram_used_mb": 512, "storage_used_gb": 5},
    )
    assert heartbeat_resp.status_code == 204

    return body
