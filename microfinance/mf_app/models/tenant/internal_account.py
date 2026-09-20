"""Institution-internal bookkeeping accounts (cash/till, and — from Phase 9.4 —
other ledger accounts like interest income). Cf. docs/architecture/08 §8.7: the
ledger's double entries always balance a customer-facing account (SavingsAccount,
Loan) against one of these. One row per institution is created for "cash" at
onboarding time; see mf_app/services/onboarding.py."""

from __future__ import annotations

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin


class InternalAccount(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "internal_accounts"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    # Asset accounts (cash) have a normal DEBIT balance; the ledger engine
    # (mf_app/services/ledger.py) uses this to know which side increases the
    # balance — never hardcoded per call site.
    normal_balance_side: Mapped[str] = mapped_column(String(10), nullable=False)
    balance_cached: Mapped[Numeric] = mapped_column(
        Numeric(18, 2), default=0, nullable=False
    )
