"""Phase 11 — security hardening: injection resistance, JWT tampering, tenant
isolation, rate limiting (cf. docs/architecture/04-securite-et-isolation.md,
09-plan-de-phases.md Phase 11). Confirmed gaps from the Phase 11 audit — this
codebase had exactly one tenant-isolation test and zero tests for the rest
before this file.
"""

import datetime as dt
import uuid

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services.sql_identifiers import is_valid_identifier, validate_identifier
from tests.conftest import register_and_login
from tests.factories import create_region, register_and_activate_node

_INJECTION_PAYLOADS = [
    "'; DROP TABLE users; --",
    '" OR "1"="1',
    "robert'); DROP TABLE students;--",
    "admin' --",
    "../../etc/passwd",
    "a" * 200,
    "",
]


@pytest.mark.parametrize("payload", _INJECTION_PAYLOADS)
def test_identifier_validation_rejects_injection_payloads(payload):
    assert is_valid_identifier(payload) is False
    with pytest.raises(ValueError):
        validate_identifier(payload)


def test_identifier_validation_accepts_legitimate_identifiers():
    assert is_valid_identifier("app_role_1") is True
    assert is_valid_identifier("readonly") is True


async def test_malicious_database_name_rejected_by_schema_before_any_sql(
    client: AsyncClient,
):
    """The Pydantic pattern on DatabaseCreate.name is the first line of
    defense — a payload that would be dangerous in a raw DDL string never
    even reaches business logic, let alone the agent."""
    owner_headers = await register_and_login(client, "secowner1@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": "acme-sec-1"},
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

    for payload in _INJECTION_PAYLOADS:
        if payload == "":
            continue  # empty name is a separate min_length validation, not the point here
        resp = await client.post(
            f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
            json={"name": payload, "region_code": "eu-west"},
            headers=owner_headers,
        )
        assert resp.status_code == 422, f"payload {payload!r} should be rejected, got {resp.text}"


async def test_tampered_jwt_signature_is_rejected(client: AsyncClient):
    headers = await register_and_login(client, "secowner2@example.com")
    token = headers["Authorization"].removeprefix("Bearer ")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert resp.status_code == 401


async def test_jwt_signed_with_wrong_secret_is_rejected(client: AsyncClient):
    settings = get_settings()
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30)},
        "not-the-real-secret",
        algorithm=settings.jwt_algorithm,
    )
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


async def test_expired_jwt_is_rejected(client: AsyncClient):
    headers = await register_and_login(client, "secowner3@example.com")
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    settings = get_settings()
    expired = jwt.encode(
        {"sub": me["id"], "exp": dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


async def test_jwt_with_algorithm_none_is_rejected(client: AsyncClient):
    """The classic "alg=none" forgery — a token with no signature at all must
    never be accepted just because it decodes."""
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30)},
        key="",
        algorithm="none",
    )
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


async def test_cross_organization_database_access_is_rejected(
    client: AsyncClient, monkeypatch
):
    admin_headers = await register_and_login(client, "secadmin1@example.com")
    from tests.conftest import promote_to_platform_admin

    await promote_to_platform_admin("secadmin1@example.com")

    owner_a = await register_and_login(client, "secowner_a@example.com")
    org_a_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Org A", "slug": "acme-sec-a"},
        headers=owner_a,
    )
    assert org_a_resp.status_code == 201, org_a_resp.text
    org_a = org_a_resp.json()
    project_a = (
        await client.post(
            f"/api/v1/organizations/{org_a['id']}/projects",
            json={"name": "Shop", "slug": "shop"},
            headers=owner_a,
        )
    ).json()
    region = await create_region(client, admin_headers, "eu-sec-a")
    await register_and_activate_node(client, admin_headers, region["code"], hostname="vps-sec-a")
    database = (
        await client.post(
            f"/api/v1/organizations/{org_a['id']}/projects/{project_a['id']}/databases",
            json={"name": "production", "region_code": region["code"]},
            headers=owner_a,
        )
    ).json()["database"]

    owner_b = await register_and_login(client, "secowner_b@example.com")
    org_b = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "Org B", "slug": "acme-sec-b"},
            headers=owner_b,
        )
    ).json()
    project_b = (
        await client.post(
            f"/api/v1/organizations/{org_b['id']}/projects",
            json={"name": "Shop", "slug": "shop"},
            headers=owner_b,
        )
    ).json()

    # org B's owner must not be able to read org A's database through ANY path:
    # neither by guessing org A's own project id, nor by supplying org B's own
    # (real) project id with org A's database id.
    cross_1 = await client.get(
        f"/api/v1/organizations/{org_a['id']}/projects/{project_a['id']}/databases/{database['id']}",
        headers=owner_b,
    )
    assert cross_1.status_code == 404

    cross_2 = await client.get(
        f"/api/v1/organizations/{org_b['id']}/projects/{project_b['id']}/databases/{database['id']}",
        headers=owner_b,
    )
    assert cross_2.status_code == 404

    # And org B's owner must not read org A's billing/usage either.
    cross_3 = await client.get(
        f"/api/v1/organizations/{org_a['id']}/subscription", headers=owner_b
    )
    assert cross_3.status_code == 404


async def test_rate_limit_returns_429_after_threshold(client: AsyncClient):
    """The actual brute-force defense docs/architecture/04 §4.6 asks for:
    unauthenticated requests (login attempts) are capped per client."""
    responses = []
    for _ in range(25):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        )
        responses.append(resp)

    statuses = [r.status_code for r in responses]
    assert 429 in statuses, f"expected a 429 among {statuses}"
    limited = next(r for r in responses if r.status_code == 429)
    assert "Retry-After" in limited.headers
