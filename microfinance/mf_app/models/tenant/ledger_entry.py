from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class LedgerDirection(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class LedgerEntry(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    """Double-entry line (§8.7) — `account_id` intentionally has no foreign key:
    it can point at a SavingsAccount, a Loan (Phase 9.3), or an InternalAccount,
    each in its own table, discriminated by `account_type`. Only
    mf_app/services/ledger.py::post_transaction ever inserts these."""

    __tablename__ = "ledger_entries"

    transaction_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("transactions.id"), nullable=False, index=True
    )
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    account_id: Mapped[str] = mapped_column(GUID(), nullable=False, index=True)
    direction: Mapped[LedgerDirection] = mapped_column(
        Enum(LedgerDirection, native_enum=False, length=10), nullable=False
    )
    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
