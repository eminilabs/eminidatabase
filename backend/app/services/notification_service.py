"""Centralized notification system (point 3 of the payments/notifications
request) — the one place that knows how each event turns into an in-app
`Notification` row plus a Resend email. Two channels, always in that order: the
in-app row is written first and unconditionally (same DB transaction as the
caller), the email is best-effort — cf. `_send_email_safe` below for why a
Resend outage must never break invoice generation, payment processing, or
registration.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email_templates import render_email
from app.models.membership import Membership, MembershipRole
from app.models.notification import Notification
from app.models.user import User
from app.services import email_service

logger = logging.getLogger("notifications")


async def _send_email_safe(to: str, subject: str, text: str, html: str) -> None:
    # A notification must never break the operation it's attached to — a Resend
    # outage must not fail login/registration/invoice-generation/payment-processing.
    try:
        await email_service.send_email(to, subject, text, html=html)
    except Exception:
        logger.exception("Failed to send notification email to=%s subject=%r", to, subject)


async def _org_owner(db: AsyncSession, organization_id: uuid.UUID) -> User | None:
    """Billing-related notifications go to the organization's OWNER — the only
    role that can actually manage billing (cf. app/services/rbac.py's
    `subscription:manage` comment: admin can read invoices but does not manage
    billing, only the owner does)."""
    return (
        await db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == organization_id,
                Membership.role == MembershipRole.OWNER,
            )
        )
    ).scalar_one_or_none()


async def _notify(
    db: AsyncSession,
    user: User,
    *,
    type: str,
    title: str,
    body: str,
    template: str,
    context: dict,
    data: dict | None = None,
) -> Notification:
    notification = Notification(user_id=user.id, type=type, title=title, body=body, data=data or {})
    db.add(notification)
    html = render_email(template, **context)
    await _send_email_safe(user.email, title, body, html)
    return notification


async def notify_welcome(db: AsyncSession, user: User) -> None:
    await _notify(
        db,
        user,
        type="welcome",
        title="Welcome to eminidatabase",
        body=f"Welcome, {user.email}. Your account has been created.",
        template="welcome.html",
        context={"email": user.email},
    )


async def notify_invoice_created(
    db: AsyncSession,
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    period_end: str,
) -> None:
    owner = await _org_owner(db, organization_id)
    if owner is None:
        return
    await _notify(
        db,
        owner,
        type="invoice_created",
        title="A new invoice is ready",
        body=f"A new invoice of {amount} {currency} has been generated for your organization.",
        template="invoice_created.html",
        context={"amount": amount, "currency": currency, "period_end": period_end},
        data={"invoice_id": str(invoice_id)},
    )


async def notify_invoice_paid(
    db: AsyncSession,
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    provider: str,
) -> None:
    owner = await _org_owner(db, organization_id)
    if owner is None:
        return
    await _notify(
        db,
        owner,
        type="invoice_paid",
        title="Payment received",
        body=f"Your payment of {amount} {currency} via {provider} has been received.",
        template="invoice_paid.html",
        context={"amount": amount, "currency": currency, "provider": provider},
        data={"invoice_id": str(invoice_id), "provider": provider},
    )


async def notify_payment_failed(
    db: AsyncSession,
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    provider: str,
) -> None:
    owner = await _org_owner(db, organization_id)
    if owner is None:
        return
    await _notify(
        db,
        owner,
        type="payment_failed",
        title="Payment attempt failed",
        body=f"Your payment of {amount} {currency} via {provider} did not go through.",
        template="payment_failed.html",
        context={"amount": amount, "currency": currency, "provider": provider},
        data={"invoice_id": str(invoice_id), "provider": provider},
    )


async def notify_subscription_changed(
    db: AsyncSession, organization_id: uuid.UUID, plan_name: str
) -> None:
    owner = await _org_owner(db, organization_id)
    if owner is None:
        return
    await _notify(
        db,
        owner,
        type="subscription_changed",
        title="Your plan has changed",
        body=f"Your organization is now subscribed to the {plan_name} plan.",
        template="subscription_changed.html",
        context={"plan_name": plan_name},
        data={"plan_name": plan_name},
    )


async def notify_subscription_suspended(
    db: AsyncSession,
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
    currency: str,
) -> None:
    owner = await _org_owner(db, organization_id)
    if owner is None:
        return
    await _notify(
        db,
        owner,
        type="subscription_suspended",
        title="Access suspended — unpaid invoice",
        body=(
            f"Invoice {invoice_id} for {amount} {currency} was never paid before your next "
            "billing period started. Database access is suspended until it's settled."
        ),
        template="subscription_suspended.html",
        context={"invoice_id": invoice_id, "amount": amount, "currency": currency},
        data={"invoice_id": str(invoice_id)},
    )


async def notify_subscription_reactivated(db: AsyncSession, organization_id: uuid.UUID) -> None:
    owner = await _org_owner(db, organization_id)
    if owner is None:
        return
    await _notify(
        db,
        owner,
        type="subscription_reactivated",
        title="Access restored",
        body="Your outstanding invoice has been paid. Database access has been restored.",
        template="subscription_reactivated.html",
        context={},
    )
