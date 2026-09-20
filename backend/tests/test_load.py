"""Phase 11 — concurrency/load (cf. 09-plan-de-phases.md Phase 11). The audit
found zero tests anywhere in the platform that issue concurrent requests —
every check so far has been sequential, which can't catch a check-then-act
race in the application layer even when the underlying DB serializes writes.
"""

import asyncio

from httpx import AsyncClient

from tests.conftest import register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


async def test_concurrent_database_creation_respects_quota(client: AsyncClient):
    """free plan allows exactly 1 database — firing two creation requests at
    once must never let both through (a TOCTOU race between the quota check
    and the insert would be a real, serious billing-correctness bug)."""
    admin_headers = await register_platform_admin(client, "loadadmin1@example.com")
    owner_headers = await register_and_login(client, "loadowner1@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": "acme-load-1"},
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
    region = await create_region(client, admin_headers, "eu-load-1")
    await register_and_activate_node(client, admin_headers, region["code"], hostname="vps-load-1")

    async def _create(name: str):
        return await client.post(
            f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
            json={"name": name, "region_code": region["code"]},
            headers=owner_headers,
        )

    results = await asyncio.gather(_create("db-a"), _create("db-b"))
    statuses = sorted(r.status_code for r in results)
    assert statuses == [202, 402], f"expected exactly one success, got {statuses}"


async def test_concurrent_reads_across_many_clients_all_succeed(client: AsyncClient):
    """A basic load smoke test: a burst of concurrent, independent authenticated
    reads must all complete correctly — no shared-state corruption between
    unrelated requests handled concurrently on the same process."""
    # 8, not more: register+login is 2 unauthenticated requests each, and the
    # unauthenticated rate limit (cf. app/core/rate_limit.py) is 20/minute —
    # this stays safely under that so the test exercises concurrency, not the
    # rate limiter (which has its own dedicated test in test_security.py).
    user_count = 8
    headers_list = [
        await register_and_login(client, f"loaduser{i}@example.com") for i in range(user_count)
    ]

    async def _whoami(headers: dict):
        return await client.get("/api/v1/auth/me", headers=headers)

    results = await asyncio.gather(*(_whoami(h) for h in headers_list))
    assert all(r.status_code == 200 for r in results)
    emails = {r.json()["email"] for r in results}
    assert emails == {f"loaduser{i}@example.com" for i in range(user_count)}
