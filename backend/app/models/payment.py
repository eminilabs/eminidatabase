from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class PaymentProviderName(str, enum.Enum):
    MANUAL = "manual"
    NOWPAYMENTS = "nowpayments"
    FEDAPAY = "fedapay"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One attempt to settle an `Invoice` through a real gateway (cf.
    app/services/payment_service.py). A manual payment completes synchronously and
    never needs a row here (cf. app/services/payments.py's ManualPaymentProvider);
    crypto/mobile-money payments are asynchronous — this row exists from the moment
    the gateway is asked to collect until its webhook confirms the outcome, exactly
    like a `Job` tracks an async orchestrator operation.

    `(provider, provider_payment_id)` is the idempotency key a webhook uses to find
    this row again — the same purpose `Job.idempotency_key` and
    `WebhookDelivery`/`Webhook.encrypted_secret` (HMAC pattern) serve elsewhere in
    this codebase.
    """

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_payment_id"),
    )

    invoice_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("invoices.id"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    provider: Mapped[PaymentProviderName] = mapped_column(
        Enum(PaymentProviderName, native_enum=False, length=20), nullable=False
    )
    # Null until the gateway hands back its own transaction id (NOWPayments'
    # `payment_id`, FedaPay's `transaction.id`).
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=20),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    # Raw status string the gateway itself uses (NOWPayments: waiting/confirming/
    # finished/...; FedaPay: pending/approved/declined/...) — kept verbatim
    # alongside our own normalized `status` for support/debugging, same reasoning
    # as Job.error being kept alongside JobStatus.
    provider_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # NOWPayments-only fields — always null for fedapay/manual.
    pay_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pay_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    pay_currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
