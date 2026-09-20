"""Invoice generation — cf. docs/architecture/08 §8.12: an invoice is always
built by aggregating UsageRecord over the subscription's current billing
period, never a manually-entered total (cahier des charges §41/§45, the same
determinism rule the microfinance ledger follows). app/scheduler.py calls
generate_due_invoices() once per tick; nothing else creates an Invoice.

Billing periods are a fixed 30 days, not calendar months — avoids
end-of-February-style edge cases without pulling in a date-arithmetic
dependency; documented simplification, not an oversight.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_line_item import InvoiceLineItem
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.usage_record import UsageMetric, UsageRecord
from app.services.database_lookup import get_database_ids_for_organization

BILLING_PERIOD = dt.timedelta(days=30)
_CENTS = Decimal("0.01")


async def compute_invoice_for_subscription(db: AsyncSession, subscription: Subscription) -> Invoice:
    plan = await db.get(Plan, subscription.plan_id)
    pricing = plan.pricing
    database_ids = await get_database_ids_for_organization(db, subscription.organization_id)

    total = Decimal("0")
    line_items: list[dict] = []

    base_fee = Decimal(str(pricing.get("base_fee", "0")))
    if base_fee > 0:
        line_items.append(
            {
                "description": "Base subscription fee",
                "metric": "base_fee",
                "quantity": Decimal("1"),
                "unit_price": base_fee,
                "amount": base_fee,
            }
        )
        total += base_fee

    if database_ids:
        for metric in UsageMetric:
            rate = pricing.get(metric.value)
            if rate is None:
                continue
            rate = Decimal(str(rate))
            quantity = Decimal(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(UsageRecord.value), 0)).where(
                            UsageRecord.database_id.in_(database_ids),
                            UsageRecord.metric == metric,
                            UsageRecord.period_start >= subscription.current_period_start,
                            UsageRecord.period_start < subscription.current_period_end,
                        )
                    )
                ).scalar_one()
            )
            if quantity == 0:
                continue
            amount = (quantity * rate).quantize(_CENTS, rounding=ROUND_HALF_UP)
            line_items.append(
                {
                    "description": f"{metric.value} usage",
                    "metric": metric.value,
                    "quantity": quantity,
                    "unit_price": rate,
                    "amount": amount,
                }
            )
            total += amount

    invoice = Invoice(
        organization_id=subscription.organization_id,
        subscription_id=subscription.id,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        status=InvoiceStatus.FINALIZED,
        total_amount=total,
        finalized_at=utcnow(),
    )
    db.add(invoice)
    await db.flush()
    for item in line_items:
        db.add(InvoiceLineItem(invoice_id=invoice.id, **item))

    subscription.current_period_start = subscription.current_period_end
    subscription.current_period_end = subscription.current_period_end + BILLING_PERIOD

    return invoice
