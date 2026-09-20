from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership, require_platform_admin
from app.db.session import get_db
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_line_item import InvoiceLineItem
from app.models.membership import Membership
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.schemas.billing import (
    CryptoPaymentRequest,
    InvoiceDetailResponse,
    InvoiceLineItemResponse,
    InvoiceResponse,
    MobileMoneyPaymentRequest,
    PaymentResponse,
    PlanCreate,
    PlanResponse,
    SubscriptionResponse,
    SubscriptionUpdate,
    UsageSummaryLine,
    UsageSummaryResponse,
)
from app.services import notification_service, payment_service
from app.services.database_lookup import get_database_ids_for_organization
from app.services.rbac import require_permission

plans_router = APIRouter(prefix="/plans", tags=["billing"])
router = APIRouter(prefix="/organizations/{organization_id}", tags=["billing"])


async def _get_subscription_or_404(db: AsyncSession, organization_id: uuid.UUID) -> Subscription:
    subscription = (
        await db.execute(
            select(Subscription).where(Subscription.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No subscription found")
    return subscription


@plans_router.post(
    "", response_model=PlanResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_admin)],
)
async def create_plan(payload: PlanCreate, db: AsyncSession = Depends(get_db)) -> Plan:
    existing = (
        await db.execute(select(Plan).where(Plan.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A plan with that name already exists"
        )
    plan = Plan(name=payload.name, quotas=payload.quotas, pricing=payload.pricing)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@plans_router.get("", response_model=list[PlanResponse])
async def list_plans(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Plan]:
    result = await db.execute(select(Plan).where(Plan.is_active.is_(True)))
    return list(result.scalars().all())


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    require_permission(membership.role, "billing:read")
    return await _get_subscription_or_404(db, organization_id)


@router.patch("/subscription", response_model=SubscriptionResponse)
async def update_subscription(
    organization_id: uuid.UUID,
    payload: SubscriptionUpdate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    require_permission(membership.role, "subscription:manage")
    subscription = await _get_subscription_or_404(db, organization_id)
    plan = await db.get(Plan, payload.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown or inactive plan")

    # docs/architecture/04 §4.5: MFA becomes mandatory for the owner/admin of a
    # paying organization once billing exists (left "to decide in Phase 10" —
    # Phase 10 shipped billing itself without deciding it; closed here in
    # Phase 11 instead of leaving it silently undone). "Paying" is defined by
    # economics (a non-zero base_fee), not by matching a plan name string.
    is_paying_plan = Decimal(str(plan.pricing.get("base_fee", "0"))) > 0
    if is_paying_plan and not current_user.mfa_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Enable MFA on your account before upgrading to a paying plan",
        )

    subscription.plan_id = plan.id
    await notification_service.notify_subscription_changed(db, organization_id, plan.name)
    await db.commit()
    await db.refresh(subscription)
    return subscription


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryResponse:
    require_permission(membership.role, "billing:read")
    subscription = await _get_subscription_or_404(db, organization_id)

    database_ids = await get_database_ids_for_organization(db, organization_id)
    lines: list[UsageSummaryLine] = []
    if database_ids:
        result = await db.execute(
            select(UsageRecord.metric, func.coalesce(func.sum(UsageRecord.value), 0))
            .where(
                UsageRecord.database_id.in_(database_ids),
                UsageRecord.period_start >= subscription.current_period_start,
                UsageRecord.period_start < subscription.current_period_end,
            )
            .group_by(UsageRecord.metric)
        )
        lines = [
            UsageSummaryLine(metric=metric.value, total=total) for metric, total in result.all()
        ]

    return UsageSummaryResponse(
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        lines=lines,
    )


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[Invoice]:
    require_permission(membership.role, "billing:read")
    result = await db.execute(
        select(Invoice)
        .where(Invoice.organization_id == organization_id)
        .order_by(Invoice.period_start.desc())
    )
    return list(result.scalars().all())


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> Invoice:
    require_permission(membership.role, "billing:read")
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    line_items = (
        (
            await db.execute(
                select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
            )
        )
        .scalars()
        .all()
    )
    # InvoiceDetailResponse.line_items is required, and the ORM object has no
    # such attribute — model_validate(invoice) alone fails before a
    # model_copy(update=...) ever gets a chance to fill it in. Build the base
    # fields from InvoiceResponse (which does validate straight off the ORM
    # object) and construct the detail response directly instead.
    base = InvoiceResponse.model_validate(invoice, from_attributes=True)
    return InvoiceDetailResponse(
        **base.model_dump(),
        line_items=[
            InvoiceLineItemResponse.model_validate(li, from_attributes=True) for li in line_items
        ],
    )


async def _get_finalized_invoice_or_404(
    db: AsyncSession, organization_id: uuid.UUID, invoice_id: uuid.UUID
) -> Invoice:
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.status != InvoiceStatus.FINALIZED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Invoice is {invoice.status.value}, not finalized"
        )
    return invoice


@router.post("/invoices/{invoice_id}/pay", response_model=InvoiceResponse)
async def pay_invoice(
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> Invoice:
    """An owner manually confirms a bank transfer/cash payment landed. For crypto
    or mobile money, use the dedicated endpoints below instead — those settle
    asynchronously via a webhook, not immediately."""
    require_permission(membership.role, "subscription:manage")
    invoice = await _get_finalized_invoice_or_404(db, organization_id, invoice_id)
    await payment_service.pay_invoice_manually(db, invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


@router.post(
    "/invoices/{invoice_id}/pay/crypto",
    response_model=PaymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def pay_invoice_with_crypto(
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: CryptoPaymentRequest,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> Payment:
    """Creates a NOWPayments deposit address for this invoice. The invoice is
    marked paid only once the NOWPayments webhook confirms the deposit — poll
    GET .../invoices/{id}/payments or wait for that confirmation."""
    require_permission(membership.role, "subscription:manage")
    invoice = await _get_finalized_invoice_or_404(db, organization_id, invoice_id)
    payment = await payment_service.initiate_crypto_payment(db, invoice, payload.pay_currency)
    await db.commit()
    await db.refresh(payment)
    return payment


@router.post(
    "/invoices/{invoice_id}/pay/mobile-money",
    response_model=PaymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def pay_invoice_with_mobile_money(
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: MobileMoneyPaymentRequest,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Payment:
    """Initiates a direct FedaPay mobile money charge — no redirect to a hosted
    checkout page. The customer approves via a USSD/app prompt on their own
    phone; the invoice is marked paid only once FedaPay's webhook confirms
    approval."""
    require_permission(membership.role, "subscription:manage")
    invoice = await _get_finalized_invoice_or_404(db, organization_id, invoice_id)
    payment = await payment_service.initiate_mobile_money_payment(
        db,
        invoice,
        mode=payload.mode,
        phone_number=payload.phone_number,
        customer_email=current_user.email,
    )
    await db.commit()
    await db.refresh(payment)
    return payment


@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentResponse])
async def list_invoice_payments(
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[Payment]:
    require_permission(membership.role, "billing:read")
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    result = await db.execute(
        select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.created_at.desc())
    )
    return list(result.scalars().all())
