from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class SavingsAccountStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class SavingsAccount(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "savings_accounts"

    customer_id: Mapped[str] = mapped_column(GUID(), ForeignKey("customers.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("savings_products.id"), nullable=False
    )
    # System-generated, distinct from any customer-facing label — same
    # collision-avoidance reasoning as the platform's own Database.physical_name
    # (cf. docs/architecture/08 §8.6).
    account_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    status: Mapped[SavingsAccountStatus] = mapped_column(
        Enum(SavingsAccountStatus, native_enum=False, length=20),
        default=SavingsAccountStatus.ACTIVE,
        nullable=False,
    )
    # Denormalized read optimization ONLY — never written directly outside
    # mf_app/services/ledger.py; reconstructible at any time from LedgerEntry
    # rows (cf. §8.7).
    balance_cached: Mapped[Numeric] = mapped_column(
        Numeric(18, 2), default=0, nullable=False
    )
