"""Orchestrates real payment gateways against `Invoice`/`Payment` (cahier des
charges §47, closing the gap `app/services/payments.py` documents). Manual
payment (`pay_invoice_manually`) completes synchronously exactly as before;
crypto (NOWPayments) and mobile money (FedaPay) are asynchronous — initiating
one creates a `Payment` row and returns immediately, and only the matching
inbound webhook (verified, then handled here) settles it.

Webhooks update state directly in the request handler rather than going through
the `jobs`/worker queue: unlike this platform's own OUTBOUND webhook deliveries
(app/services/webhook_orchestrator.py, which must retry against a third party's
unreliable endpoint), handling an INBOUND webhook is a single fast DB write with
no external call to retry — there's nothing here that benefits from a queue.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentProviderName, PaymentStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.services import notification_service
from app.services.payment_providers import fedapay, nowpayments
from app.services.payments import ManualPaymentProvider
from app.services.webhook_orchestrator import emit_event


class PaymentWebhookError(RuntimeError):
    pass


async def _mark_invoice_paid(
    db: AsyncSession, invoice: Invoice, *, provider: str, provider_reference: str
) -> None:
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = utcnow()
    invoice.payment_reference = provider_reference
    await notification_service.notify_invoice_paid(
        db, invoice.organization_id, invoice.id, invoice.total_amount, invoice.currency, provider
    )
    await emit_event(
        db,
        invoice.organization_id,
        "invoice.paid",
        {
            "invoice_id": str(invoice.id),
            "amount": str(invoice.total_amount),
            "currency": invoice.currency,
        },
    )
    await _reactivate_if_current(db, invoice)


async def _reactivate_if_current(db: AsyncSession, invoice: Invoice) -> None:
    """Paying off the invoice that got an organization suspended
    (app/scheduler.py's generate_due_invoices, when a new billing period
    starts with the previous one still unpaid) should restore access as soon
    as no unpaid invoice remains — not require a platform admin to
    manually flip the subscription back on."""
    subscription = await db.get(Subscription, invoice.subscription_id)
    if subscription is None or subscription.status != SubscriptionStatus.PAST_DUE:
        return
    # Sessions here run with autoflush=False (app/db/session.py), so the
    # in-memory `invoice.status = PAID` set just above isn't visible to this
    # SELECT yet — exclude this invoice by id explicitly rather than relying
    # on a flush to have happened first.
    still_unpaid = (
        await db.execute(
            select(Invoice.id).where(
                Invoice.subscription_id == subscription.id,
                Invoice.status == InvoiceStatus.FINALIZED,
                Invoice.id != invoice.id,
            )
        )
    ).first()
    if still_unpaid is None:
        subscription.status = SubscriptionStatus.ACTIVE
        await notification_service.notify_subscription_reactivated(db, invoice.organization_id)


async def pay_invoice_manually(db: AsyncSession, invoice: Invoice) -> Invoice:
    provider = ManualPaymentProvider()
    result = await provider.charge(
        organization_reference=str(invoice.organization_id),
        amount=invoice.total_amount,
        currency=invoice.currency,
        reference=str(invoice.id),
    )
    await _mark_invoice_paid(
        db, invoice, provider="manual", provider_reference=result.provider_reference
    )
    return invoice


async def initiate_crypto_payment(
    db: AsyncSession, invoice: Invoice, pay_currency: str | None
) -> Payment:
    settings = get_settings()
    currency = pay_currency or settings.nowpayments_default_pay_currency
    window_hours = settings.nowpayments_payment_window_hours
    response = await nowpayments.create_payment(
        price_amount=float(invoice.total_amount),
        price_currency=invoice.currency.lower(),
        order_id=str(invoice.id),
        order_description=f"eminidatabase invoice {invoice.id}",
        pay_currency=currency,
    )
    raw_pay_amount = response.get("pay_amount")
    payment = Payment(
        invoice_id=invoice.id,
        organization_id=invoice.organization_id,
        provider=PaymentProviderName.NOWPAYMENTS,
        provider_payment_id=str(response["payment_id"]),
        amount=invoice.total_amount,
        currency=invoice.currency,
        status=PaymentStatus.PENDING,
        provider_status=response.get("payment_status"),
        pay_address=response.get("pay_address"),
        pay_amount=Decimal(str(raw_pay_amount)) if raw_pay_amount is not None else None,
        pay_currency=response.get("pay_currency"),
        payment_expires_at=utcnow() + dt.timedelta(hours=window_hours),
    )
    db.add(payment)
    await db.flush()
    return payment


async def initiate_mobile_money_payment(
    db: AsyncSession, invoice: Invoice, *, mode: str, phone_number: str, customer_email: str
) -> Payment:
    if mode not in fedapay.MOBILE_MONEY_OPERATORS:
        raise fedapay.FedaPayError(f"Unsupported mobile money mode: {mode!r}")

    transaction_id = await fedapay.create_transaction(
        amount=int(invoice.total_amount),
        currency=invoice.currency,
        description=f"eminidatabase invoice {invoice.id}",
        customer_email=customer_email,
    )
    token = await fedapay.generate_token(transaction_id)

    payment = Payment(
        invoice_id=invoice.id,
        organization_id=invoice.organization_id,
        provider=PaymentProviderName.FEDAPAY,
        provider_payment_id=transaction_id,
        amount=invoice.total_amount,
        currency=invoice.currency,
        status=PaymentStatus.PENDING,
        provider_status="pending",
    )
    db.add(payment)
    # Committed now, before the charge call — proven necessary live: a client-side
    # timeout on charge_mobile_money does NOT mean the charge didn't reach FedaPay
    # (it can still show up, and even get approved, on their side). If this row
    # were only flushed and the charge call then raised, the FastAPI session
    # dependency rolls back on the propagated exception and this record — the only
    # link to `transaction_id` — would vanish, leaving a real charge attempt with
    # no local trace to reconcile against a late webhook or a status poll.
    await db.commit()
    await db.refresh(payment)

    try:
        await fedapay.charge_mobile_money(token=token, mode=mode, phone_number=phone_number)
    except (fedapay.FedaPayError, httpx.HTTPError) as exc:
        # Genuinely unknown outcome at this point, not a confirmed failure — leave
        # `status` PENDING and let the webhook or a reconciliation poll (cf.
        # fedapay.get_transaction_status) determine the truth later.
        payment.error = str(exc)[:2000]
        await db.commit()
        await db.refresh(payment)

    return payment


async def handle_nowpayments_webhook(
    db: AsyncSession, payload_bytes: bytes, signature: str
) -> None:
    if not nowpayments.verify_ipn_signature(payload_bytes, signature):
        raise PaymentWebhookError("Invalid NOWPayments IPN signature")

    payload = json.loads(payload_bytes)
    provider_payment_id = str(payload.get("payment_id"))
    payment_status = payload.get("payment_status")
    actually_paid = Decimal(str(payload.get("actually_paid") or "0"))
    price_amount = Decimal(str(payload.get("price_amount") or "0"))

    payment = (
        await db.execute(
            select(Payment).where(
                Payment.provider == PaymentProviderName.NOWPAYMENTS,
                Payment.provider_payment_id == provider_payment_id,
            )
        )
    ).scalar_one_or_none()
    if payment is None or payment.status != PaymentStatus.PENDING:
        return  # unknown, or already finalized — idempotent no-op.

    payment.provider_status = payment_status
    tolerance = Decimal(str(get_settings().nowpayments_tolerance_usd))
    shortfall = price_amount - actually_paid

    settled_within_tolerance = payment_status == "partially_paid" and shortfall <= tolerance
    if payment_status == "finished" or settled_within_tolerance:
        await _finalize_payment(db, payment)
    elif payment_status in ("failed", "expired") and actually_paid == 0:
        payment.status = PaymentStatus.FAILED
        invoice = await db.get(Invoice, payment.invoice_id)
        if invoice is not None:
            await notification_service.notify_payment_failed(
                db,
                invoice.organization_id,
                invoice.id,
                invoice.total_amount,
                invoice.currency,
                "nowpayments",
            )
    # else: still in flight (waiting/confirming/...) — leave PENDING.


async def handle_fedapay_webhook(
    db: AsyncSession, payload_bytes: bytes, signature_header: str
) -> None:
    if not fedapay.verify_webhook_signature(payload_bytes, signature_header):
        raise PaymentWebhookError("Invalid FedaPay webhook signature")

    payload = json.loads(payload_bytes)
    entity = payload.get("entity") or {}
    provider_payment_id = str(entity.get("id"))
    entity_status = entity.get("status")

    payment = (
        await db.execute(
            select(Payment).where(
                Payment.provider == PaymentProviderName.FEDAPAY,
                Payment.provider_payment_id == provider_payment_id,
            )
        )
    ).scalar_one_or_none()
    if payment is None or payment.status != PaymentStatus.PENDING:
        return  # unknown, or already finalized — idempotent no-op.

    if entity_status == "approved":
        payment.provider_status = entity_status
        await _finalize_payment(db, payment)
    elif entity_status in ("declined", "canceled"):
        payment.provider_status = entity_status
        payment.status = PaymentStatus.FAILED
        invoice = await db.get(Invoice, payment.invoice_id)
        if invoice is not None:
            await notification_service.notify_payment_failed(
                db,
                invoice.organization_id,
                invoice.id,
                invoice.total_amount,
                invoice.currency,
                "fedapay",
            )
    # else (e.g. "pending", or the "transaction.created" event that fires before
    # any payment attempt): not a terminal outcome yet — deliberately don't touch
    # `status`, or a real later "approved" webhook could arrive after this one
    # already flipped the payment to FAILED and be silently ignored.


async def _finalize_payment(db: AsyncSession, payment: Payment) -> None:
    if payment.status == PaymentStatus.SUCCEEDED:
        return  # idempotent — a retried webhook delivery must not double-apply.
    payment.status = PaymentStatus.SUCCEEDED
    invoice = await db.get(Invoice, payment.invoice_id)
    if invoice is None or invoice.status == InvoiceStatus.PAID:
        return
    await _mark_invoice_paid(
        db, invoice, provider=payment.provider.value, provider_reference=str(payment.id)
    )
