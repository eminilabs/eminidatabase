"""Phase 10 — plans/subscriptions/quotas/usage metering/invoice generation
(cf. docs/architecture/08 §8.12, 09-plan-de-phases.md Phase 10)."""

import datetime as dt
import uuid
from decimal import Decimal

import pyotp
from httpx import AsyncClient
from sqlalchemy import select

import app.scheduler as scheduler_module
import app.worker as worker_module
from app.core.timeutil import as_aware_utc, utcnow
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_line_item import InvoiceLineItem
from app.models.subscription import Subscription
from app.models.usage_record import UsageMetric, UsageRecord
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _MetricsAgentResponse:
    def __init__(self, size_bytes: int, active_connections: int):
        self._body = {
            "size_bytes": size_bytes,
            "active_connections": active_connections,
            "max_connections": 100,
        }

    def json(self):
        return self._body


async def _fake_call_agent_generic(node, method, path, *, json=None, params=None, timeout=30.0):
    class _Resp:
        def json(self_inner):
            return {"status": "ok"}

    return _Resp()


async def _run_worker_tick(monkeypatch) -> bool:
    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent_generic)
    return await worker_module.run_once()


async def _setup_org_project_node(
    client: AsyncClient, admin_headers: dict, suffix: str
) -> tuple[dict, dict, dict, dict]:
    owner_headers = await register_and_login(client, f"billowner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": f"acme-bill-{suffix}"},
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
    region = await create_region(client, admin_headers, f"eu-bill-{suffix}")
    await register_and_activate_node(
        client, admin_headers, region["code"], hostname=f"vps-bill-{suffix}"
    )
    return owner_headers, org, project, region


async def _get_plan_id(client: AsyncClient, headers: dict, name: str) -> str:
    plans = (await client.get("/api/v1/plans", headers=headers)).json()
    return next(p["id"] for p in plans if p["name"] == name)


async def _enable_mfa(client: AsyncClient, headers: dict) -> None:
    enable_resp = await client.post("/api/v1/auth/mfa/enable", headers=headers)
    assert enable_resp.status_code == 200, enable_resp.text
    uri = enable_resp.json()["provisioning_uri"]
    secret = dict(part.split("=") for part in uri.split("?")[1].split("&"))["secret"]
    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/auth/mfa/verify", json={"otp_code": code}, headers=headers
    )
    assert verify_resp.status_code == 204, verify_resp.text


async def test_new_organization_gets_free_subscription(client: AsyncClient):
    owner_headers = await register_and_login(client, "freeorg@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "Free Org", "slug": "free-org"},
            headers=owner_headers,
        )
    ).json()

    sub_resp = await client.get(
        f"/api/v1/organizations/{org['id']}/subscription", headers=owner_headers
    )
    assert sub_resp.status_code == 200, sub_resp.text
    subscription = sub_resp.json()

    free_plan_id = await _get_plan_id(client, owner_headers, "free")
    assert subscription["plan_id"] == free_plan_id
    assert subscription["status"] == "active"


async def test_database_creation_blocked_when_databases_quota_exceeded(
    client: AsyncClient, monkeypatch
):
    admin_headers = await register_platform_admin(client, "billadmin1@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "quota1"
    )

    # free plan allows exactly 1 database.
    first = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "db-one", "region_code": region["code"]},
        headers=owner_headers,
    )
    assert first.status_code == 202, first.text

    second = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "db-two", "region_code": region["code"]},
        headers=owner_headers,
    )
    assert second.status_code == 402, second.text


async def test_database_creation_blocked_when_storage_quota_exceeded(
    client: AsyncClient, monkeypatch
):
    admin_headers = await register_platform_admin(client, "billadmin2@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "quota2"
    )

    # free plan allows 20 GB total — a single 25 GB request must be rejected.
    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "big-db", "region_code": region["code"], "storage_limit_gb": 25},
        headers=owner_headers,
    )
    assert resp.status_code == 402, resp.text


async def test_owner_can_upgrade_plan_developer_cannot(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "billadmin3@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "upgrade1"
    )
    pro_plan_id = await _get_plan_id(client, owner_headers, "pro")

    dev_headers = await register_and_login(client, "billdev1@example.com")
    dev_me = (await client.get("/api/v1/auth/me", headers=dev_headers)).json()
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": dev_me["email"], "role": "developer"},
        headers=owner_headers,
    )

    forbidden = await client.patch(
        f"/api/v1/organizations/{org['id']}/subscription",
        json={"plan_id": pro_plan_id},
        headers=dev_headers,
    )
    assert forbidden.status_code == 403

    # pro is a paying plan (non-zero base_fee) — the owner needs MFA first
    # (docs/architecture/04 §4.5, enforced in Phase 11; see the dedicated test
    # below for the rejection path).
    await _enable_mfa(client, owner_headers)

    allowed = await client.patch(
        f"/api/v1/organizations/{org['id']}/subscription",
        json={"plan_id": pro_plan_id},
        headers=owner_headers,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["plan_id"] == pro_plan_id


async def test_upgrading_to_paying_plan_requires_mfa(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "billadmin6@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "mfa1"
    )
    pro_plan_id = await _get_plan_id(client, owner_headers, "pro")

    without_mfa = await client.patch(
        f"/api/v1/organizations/{org['id']}/subscription",
        json={"plan_id": pro_plan_id},
        headers=owner_headers,
    )
    assert without_mfa.status_code == 403, without_mfa.text

    await _enable_mfa(client, owner_headers)
    with_mfa = await client.patch(
        f"/api/v1/organizations/{org['id']}/subscription",
        json={"plan_id": pro_plan_id},
        headers=owner_headers,
    )
    assert with_mfa.status_code == 200, with_mfa.text


async def test_meter_usage_records_real_agent_metrics(client: AsyncClient, monkeypatch):
    admin_headers = await register_platform_admin(client, "billadmin4@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "meter1"
    )
    # free plan caps max_cpu_total at 1 — upgrade so cpu_limit=2 below is allowed.
    # pro is a paying plan, so MFA is required first (Phase 11, §4.5).
    pro_plan_id = await _get_plan_id(client, owner_headers, "pro")
    await _enable_mfa(client, owner_headers)
    upgrade_resp = await client.patch(
        f"/api/v1/organizations/{org['id']}/subscription",
        json={"plan_id": pro_plan_id},
        headers=owner_headers,
    )
    assert upgrade_resp.status_code == 200, upgrade_resp.text

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={
            "name": "metered-db",
            "region_code": region["code"],
            "cpu_limit": 2,
            "storage_limit_gb": 2,
        },
        headers=owner_headers,
    )
    assert create_resp.status_code == 202, create_resp.text
    database_id = create_resp.json()["database"]["id"]
    assert await _run_worker_tick(monkeypatch) is True

    get_resp = await client.get(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}",
        headers=owner_headers,
    )
    assert get_resp.json()["status"] == "running"

    async def _fake_metrics_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        assert path.endswith("/metrics")
        return _MetricsAgentResponse(size_bytes=2 * 1024**3, active_connections=7)

    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(scheduler_module, "call_agent", _fake_metrics_agent)

    metered_count = await scheduler_module.meter_usage()
    assert metered_count == 1

    async with TestSessionLocal() as db:
        records = (
            (
                await db.execute(
                    select(UsageRecord).where(UsageRecord.database_id == uuid.UUID(database_id))
                )
            )
            .scalars()
            .all()
        )
    by_metric = {r.metric: r.value for r in records}
    hours = Decimal(60) / Decimal(3600)
    # The column is Numeric(18, 6) — the value read back is rounded to 6
    # decimal places, but `hours` computed fresh in Python carries the ~28
    # significant digits of the default Decimal context. Quantize the
    # expectation the same way the column does before comparing, or a
    # perfectly correct stored value looks "wrong" by a many-digits-later
    # rounding difference that was never actually a discrepancy.
    six_places = Decimal("0.000001")
    assert by_metric[UsageMetric.STORAGE_GB_HOURS] == (Decimal(2) * hours).quantize(six_places)
    assert by_metric[UsageMetric.CPU_HOURS] == (Decimal(2) * hours).quantize(six_places)
    assert by_metric[UsageMetric.CONNECTIONS] == Decimal(7)


async def test_invoice_generation_aggregates_usage_and_advances_period(
    client: AsyncClient, monkeypatch
):
    admin_headers = await register_platform_admin(client, "billadmin5@example.com")
    owner_headers, org, project, region = await _setup_org_project_node(
        client, admin_headers, "invoice1"
    )
    pro_plan_id = await _get_plan_id(client, owner_headers, "pro")
    await _enable_mfa(client, owner_headers)
    await client.patch(
        f"/api/v1/organizations/{org['id']}/subscription",
        json={"plan_id": pro_plan_id},
        headers=owner_headers,
    )

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "invoiced-db", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = uuid.UUID(create_resp.json()["database"]["id"])
    assert await _run_worker_tick(monkeypatch) is True
    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", TestSessionLocal)

    # Simulate a month of accumulated ticks with clean numbers, rather than
    # relying on meter_usage()'s tiny per-tick fractions (already proven exact
    # by test_meter_usage_records_real_agent_metrics) — this test is about the
    # invoice MATH, not the metering mechanism.
    async with TestSessionLocal() as db:
        subscription = (
            await db.execute(
                select(Subscription).where(Subscription.organization_id == uuid.UUID(org["id"]))
            )
        ).scalar_one()
        period_start = subscription.current_period_start
        db.add(
            UsageRecord(
                database_id=database_id,
                metric=UsageMetric.CPU_HOURS,
                value=Decimal("100"),
                period_start=period_start,
                period_end=period_start,
            )
        )
        db.add(
            UsageRecord(
                database_id=database_id,
                metric=UsageMetric.STORAGE_GB_HOURS,
                value=Decimal("40"),
                period_start=period_start,
                period_end=period_start,
            )
        )
        # Force the subscription's billing period to already be over.
        subscription.current_period_end = utcnow() - dt.timedelta(seconds=1)
        old_period_end = subscription.current_period_end
        await db.commit()

    generated = await scheduler_module.generate_due_invoices()
    assert generated == 1

    async with TestSessionLocal() as db:
        invoice = (
            await db.execute(select(Invoice).where(Invoice.organization_id == uuid.UUID(org["id"])))
        ).scalar_one()
        line_items = (
            (
                await db.execute(
                    select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
                )
            )
            .scalars()
            .all()
        )
        subscription = await db.get(Subscription, subscription.id)

    # pro pricing: base_fee=25.00, cpu_hours=0.02/h, storage_gb_hours=0.0005/h
    # -> 25.00 + (100 * 0.02) + (40 * 0.0005) = 25.00 + 2.00 + 0.02 = 27.02
    assert invoice.status == InvoiceStatus.FINALIZED
    assert invoice.total_amount == Decimal("27.02")
    assert {li.metric for li in line_items} == {"base_fee", "cpu_hours", "storage_gb_hours"}
    # SQLite doesn't round-trip tzinfo (the same documented pitfall as
    # app/core/timeutil.py's own docstring) — normalize before comparing a
    # freshly-read value against one still held in memory from before the
    # round-trip.
    assert as_aware_utc(subscription.current_period_start) == old_period_end
    assert as_aware_utc(subscription.current_period_end) > old_period_end

    # An invoice is a real audit artifact via the API too, not just internal state.
    api_invoice = (
        await client.get(
            f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}", headers=owner_headers
        )
    ).json()
    assert api_invoice["total_amount"] == "27.02"
    assert len(api_invoice["line_items"]) == 3

    pay_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}/pay", headers=owner_headers
    )
    assert pay_resp.status_code == 200, pay_resp.text
    assert pay_resp.json()["status"] == "paid"

    second_pay = await client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}/pay", headers=owner_headers
    )
    assert second_pay.status_code == 409


async def test_platform_admin_only_can_create_plans(client: AsyncClient):
    owner_headers = await register_and_login(client, "notadmin@example.com")
    resp = await client.post(
        "/api/v1/plans",
        json={"name": "custom", "quotas": {}, "pricing": {}},
        headers=owner_headers,
    )
    assert resp.status_code == 403

    admin_headers = await register_platform_admin(client, "planadmin@example.com")
    ok = await client.post(
        "/api/v1/plans",
        json={"name": "custom", "quotas": {"max_databases": 50}, "pricing": {}},
        headers=admin_headers,
    )
    assert ok.status_code == 201, ok.text
