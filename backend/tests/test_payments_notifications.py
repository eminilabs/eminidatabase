"""Phase 12 (partial) — real NOWPayments/FedaPay gateways closing the abstraction
in app/services/payments.py, and the Resend-backed notification system
(app/services/notification_service.py). Network calls to the gateways are
monkeypatched at the `payment_providers` module boundary — the same pattern
test_billing.py uses for `call_agent`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import time

import httpx
from httpx import AsyncClient
from sqlalchemy import select

import app.scheduler as scheduler_module
import app.worker as worker_module
from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentProviderName, PaymentStatus
from app.models.subscription import Subscription
from app.services.payment_providers import fedapay, nowpayments
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _OkResp:
    def json(self):
        return {"status": "ok"}


async def _run_worker_tick(monkeypatch) -> bool:
    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(
        "app.services.orchestrator.call_agent",
        lambda node, method, path, *, json=None, params=None, timeout=30.0: _OkResp(),
    )
    return await worker_module.run_once()


async def _async_return(value):
    return value


async def _setup_paid_invoice(client: AsyncClient, suffix: str):
    """Builds an organization with a FINALIZED invoice ready to be paid — no
    project/node/database needed, since these tests exercise payment settlement,
    not usage-based invoice math (already covered by test_billing.py)."""
    owner_headers = await register_and_login(client, f"payowner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": f"acme-pay-{suffix}"},
            headers=owner_headers,
        )
    ).json()

    async with TestSessionLocal() as db:
        subscription = (
            await db.execute(
                select(Subscription).where(Subscription.organization_id == org["id"])
            )
        ).scalar_one()
        db.add(
            Invoice(
                organization_id=org["id"],
                subscription_id=subscription.id,
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end,
                status=InvoiceStatus.FINALIZED,
                total_amount="10.00",
                currency="USD",
                finalized_at=subscription.current_period_start,
            )
        )
        await db.commit()
        invoice = (
            await db.execute(select(Invoice).where(Invoice.organization_id == org["id"]))
        ).scalar_one()

    return owner_headers, org, invoice


async def test_register_sends_welcome_in_app_notification(client: AsyncClient):
    headers = await register_and_login(client, "welcome1@example.com")
    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200, resp.text
    types = [n["type"] for n in resp.json()]
    assert "welcome" in types


async def test_crypto_payment_succeeds_via_webhook(client: AsyncClient, monkeypatch):
    owner_headers, org, invoice = await _setup_paid_invoice(client, "crypto1")

    async def _fake_create_payment(
        *, price_amount, price_currency, order_id, order_description, pay_currency
    ):
        assert order_id == str(invoice.id)
        return {
            "payment_id": "np-123",
            "payment_status": "waiting",
            "pay_address": "bc1qxyz",
            "pay_amount": "0.00041",
            "pay_currency": pay_currency,
        }

    monkeypatch.setattr(nowpayments, "create_payment", _fake_create_payment)

    init_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}/pay/crypto",
        json={"pay_currency": "btc"},
        headers=owner_headers,
    )
    assert init_resp.status_code == 202, init_resp.text
    payment = init_resp.json()
    assert payment["status"] == "pending"
    assert payment["pay_address"] == "bc1qxyz"

    # Invoice must not be paid yet — only the webhook settles it.
    still_finalized = await client.get(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}", headers=owner_headers
    )
    assert still_finalized.json()["status"] == "finalized"

    monkeypatch.setattr(nowpayments, "verify_ipn_signature", lambda body, sig: True)
    webhook_body = json.dumps(
        {
            "payment_id": "np-123",
            "payment_status": "finished",
            "actually_paid": "0.00041",
            "price_amount": "10.00",
        }
    ).encode()
    webhook_headers = {
        "x-nowpayments-sig": "irrelevant-because-monkeypatched",
        "Content-Type": "application/json",
    }
    webhook_resp = await client.post(
        "/api/v1/billing/webhooks/nowpayments", content=webhook_body, headers=webhook_headers
    )
    assert webhook_resp.status_code == 204, webhook_resp.text

    paid = await client.get(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}", headers=owner_headers
    )
    assert paid.json()["status"] == "paid"

    async with TestSessionLocal() as db:
        db_payment = (
            await db.execute(select(Payment).where(Payment.invoice_id == invoice.id))
        ).scalar_one()
        assert db_payment.status == PaymentStatus.SUCCEEDED
        assert db_payment.provider == PaymentProviderName.NOWPAYMENTS

    # A second delivery of the same webhook (gateways retry) must be a no-op.
    replay_resp = await client.post(
        "/api/v1/billing/webhooks/nowpayments", content=webhook_body, headers=webhook_headers
    )
    assert replay_resp.status_code == 204, replay_resp.text


async def test_crypto_payment_rejects_bad_signature(client: AsyncClient, monkeypatch):
    owner_headers, org, invoice = await _setup_paid_invoice(client, "crypto2")

    async def _fake_create_payment(
        *, price_amount, price_currency, order_id, order_description, pay_currency
    ):
        return {
            "payment_id": "np-456",
            "payment_status": "waiting",
            "pay_address": "addr",
            "pay_amount": "1",
            "pay_currency": pay_currency,
        }

    monkeypatch.setattr(nowpayments, "create_payment", _fake_create_payment)
    await client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}/pay/crypto",
        json={},
        headers=owner_headers,
    )

    monkeypatch.setattr(nowpayments, "verify_ipn_signature", lambda body, sig: False)
    resp = await client.post(
        "/api/v1/billing/webhooks/nowpayments",
        content=b'{"payment_id": "np-456"}',
        headers={"x-nowpayments-sig": "bad", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


async def test_mobile_money_payment_succeeds_via_webhook(client: AsyncClient, monkeypatch):
    owner_headers, org, invoice = await _setup_paid_invoice(client, "momo1")

    async def _fake_create_transaction(*, amount, currency, description, customer_email):
        return "fp-tx-1"

    async def _fake_generate_token(transaction_id):
        return "tok-1"

    charged = {}

    async def _fake_charge_mobile_money(*, token, mode, phone_number):
        charged["mode"] = mode
        charged["phone_number"] = phone_number

    monkeypatch.setattr(fedapay, "create_transaction", _fake_create_transaction)
    monkeypatch.setattr(fedapay, "generate_token", _fake_generate_token)
    monkeypatch.setattr(fedapay, "charge_mobile_money", _fake_charge_mobile_money)

    init_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}/pay/mobile-money",
        json={"mode": "mtn_ci", "phone_number": "0102030405"},
        headers=owner_headers,
    )
    assert init_resp.status_code == 202, init_resp.text
    assert charged == {"mode": "mtn_ci", "phone_number": "0102030405"}
    payment = init_resp.json()
    assert payment["provider"] == "fedapay"
    assert payment["status"] == "pending"

    monkeypatch.setattr(fedapay, "verify_webhook_signature", lambda body, sig: True)

    # The "created" event fires before any real approval and must not be treated
    # as a terminal outcome (cf. payment_service.handle_fedapay_webhook).
    created_body = json.dumps(
        {"name": "transaction.created", "entity": {"id": "fp-tx-1", "status": "pending"}}
    ).encode()
    r1 = await client.post(
        "/api/v1/billing/webhooks/fedapay",
        content=created_body,
        headers={"x-fedapay-signature": "t=1,s=irrelevant"},
    )
    assert r1.status_code == 204

    still_finalized = await client.get(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}", headers=owner_headers
    )
    assert still_finalized.json()["status"] == "finalized"

    approved_body = json.dumps(
        {"name": "transaction.approved", "entity": {"id": "fp-tx-1", "status": "approved"}}
    ).encode()
    r2 = await client.post(
        "/api/v1/billing/webhooks/fedapay",
        content=approved_body,
        headers={"x-fedapay-signature": "t=1,s=irrelevant"},
    )
    assert r2.status_code == 204

    paid = await client.get(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}", headers=owner_headers
    )
    assert paid.json()["status"] == "paid"


async def test_mobile_money_charge_timeout_still_persists_payment_for_reconciliation(
    client: AsyncClient, monkeypatch
):
    """Live-verified scenario (2026-09-20): a client-side timeout on
    `charge_mobile_money` does NOT mean FedaPay never received the charge — it can
    still show up, and even get approved, on their side. The `Payment` row (the
    only local link to `provider_payment_id`) must survive this, not roll back
    with the exception, or a later webhook/reconciliation poll would have nothing
    to match against."""
    owner_headers, org, invoice = await _setup_paid_invoice(client, "momo3")

    monkeypatch.setattr(fedapay, "create_transaction", lambda **kw: _async_return("fp-tx-3"))
    monkeypatch.setattr(fedapay, "generate_token", lambda transaction_id: _async_return("tok-3"))

    async def _fake_charge_times_out(*, token, mode, phone_number):
        raise httpx.ReadTimeout("simulated network timeout")

    monkeypatch.setattr(fedapay, "charge_mobile_money", _fake_charge_times_out)

    init_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}/pay/mobile-money",
        json={"mode": "moov", "phone_number": "0102030405"},
        headers=owner_headers,
    )
    assert init_resp.status_code == 202, init_resp.text
    payment = init_resp.json()
    assert payment["provider"] == "fedapay"
    assert payment["provider_payment_id"] == "fp-tx-3"
    assert payment["status"] == "pending"

    async with TestSessionLocal() as db:
        db_payment = (
            await db.execute(select(Payment).where(Payment.invoice_id == invoice.id))
        ).scalar_one()
        assert db_payment.provider_payment_id == "fp-tx-3"
        assert db_payment.error is not None

    # A late webhook confirming approval must still be able to find and settle it.
    monkeypatch.setattr(fedapay, "verify_webhook_signature", lambda body, sig: True)
    approved_body = json.dumps(
        {"name": "transaction.approved", "entity": {"id": "fp-tx-3", "status": "approved"}}
    ).encode()
    resp = await client.post(
        "/api/v1/billing/webhooks/fedapay",
        content=approved_body,
        headers={"x-fedapay-signature": "t=1,s=irrelevant"},
    )
    assert resp.status_code == 204

    paid = await client.get(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}", headers=owner_headers
    )
    assert paid.json()["status"] == "paid"


async def test_mobile_money_payment_failure_notifies_and_marks_payment_failed(
    client: AsyncClient, monkeypatch
):
    owner_headers, org, invoice = await _setup_paid_invoice(client, "momo2")

    monkeypatch.setattr(fedapay, "create_transaction", lambda **kw: _async_return("fp-tx-2"))
    monkeypatch.setattr(fedapay, "generate_token", lambda transaction_id: _async_return("tok-2"))
    monkeypatch.setattr(fedapay, "charge_mobile_money", lambda **kw: _async_return(None))

    await client.post(
        f"/api/v1/organizations/{org['id']}/invoices/{invoice.id}/pay/mobile-money",
        json={"mode": "moov", "phone_number": "0102030405"},
        headers=owner_headers,
    )

    monkeypatch.setattr(fedapay, "verify_webhook_signature", lambda body, sig: True)
    declined_body = json.dumps(
        {"name": "transaction.declined", "entity": {"id": "fp-tx-2", "status": "declined"}}
    ).encode()
    resp = await client.post(
        "/api/v1/billing/webhooks/fedapay",
        content=declined_body,
        headers={"x-fedapay-signature": "t=1,s=irrelevant"},
    )
    assert resp.status_code == 204

    async with TestSessionLocal() as db:
        db_payment = (
            await db.execute(select(Payment).where(Payment.invoice_id == invoice.id))
        ).scalar_one()
        assert db_payment.status == PaymentStatus.FAILED

    notifications = (await client.get("/api/v1/notifications", headers=owner_headers)).json()
    assert any(n["type"] == "payment_failed" for n in notifications)


def test_nowpayments_ipn_signature_roundtrip(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "nowpayments_ipn_secret", "shh")
    body = {"payment_id": "1", "payment_status": "finished"}
    sorted_body = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sig = hmac.new(b"shh", sorted_body.encode(), hashlib.sha512).hexdigest()
    assert nowpayments.verify_ipn_signature(json.dumps(body).encode(), sig)
    assert not nowpayments.verify_ipn_signature(json.dumps(body).encode(), "wrong")


def test_fedapay_webhook_signature_roundtrip(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "fedapay_webhook_secret", "shh")
    body = b'{"entity": {"id": "1"}}'
    ts = str(int(time.time()))
    sig = hmac.new(b"shh", f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    assert fedapay.verify_webhook_signature(body, f"t={ts},s={sig}")
    assert not fedapay.verify_webhook_signature(body, f"t={ts},s=wrong")


async def _bill_setup(client: AsyncClient, admin_headers: dict, suffix: str):
    owner_headers = await register_and_login(client, f"billnotif{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": f"acme-notif-{suffix}"},
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
    region = await create_region(client, admin_headers, f"eu-notif-{suffix}")
    await register_and_activate_node(
        client, admin_headers, region["code"], hostname=f"vps-notif-{suffix}"
    )
    return owner_headers, org, project, region


async def test_invoice_generation_sends_invoice_created_notification(
    client: AsyncClient, monkeypatch
):
    admin_headers = await register_platform_admin(client, "payadmin5@example.com")
    owner_headers, org, project, region = await _bill_setup(client, admin_headers, "notif1")

    await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "invoiced-db", "region_code": region["code"]},
        headers=owner_headers,
    )
    assert await _run_worker_tick(monkeypatch) is True
    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", TestSessionLocal)

    async with TestSessionLocal() as db:
        subscription = (
            await db.execute(
                select(Subscription).where(Subscription.organization_id == org["id"])
            )
        ).scalar_one()
        subscription.current_period_end = utcnow() - dt.timedelta(seconds=1)
        await db.commit()

    generated = await scheduler_module.generate_due_invoices()
    assert generated == 1

    notifications = (await client.get("/api/v1/notifications", headers=owner_headers)).json()
    assert any(n["type"] == "invoice_created" for n in notifications)
