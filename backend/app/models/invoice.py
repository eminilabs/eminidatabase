from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"
    VOID = "void"


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """cf. docs/architecture/08 §8.12 — generated from UsageRecord aggregated
    over the Subscription's billing period, never a manually-entered amount
    (cahier des charges §41/§45, same determinism rule as the microfinance
    ledger). One row per (organization, billing period)."""

    __tablename__ = "invoices"

    organization_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    subscription_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("subscriptions.id"), nullable=False
    )
    period_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, native_enum=False, length=20),
        default=InvoiceStatus.DRAFT,
        nullable=False,
    )
    total_amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    finalized_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Opaque reference from whatever PaymentProvider handled it (cf.
    # app/services/payments.py) — never a raw card/account number.
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
