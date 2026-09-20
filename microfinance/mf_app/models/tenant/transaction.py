from __future__ import annotations

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    """One financial event (§8.7) — never mutated after creation. Always paired
    with balanced LedgerEntry rows by mf_app/services/ledger.py::post_transaction,
    the only code allowed to create either."""

    __tablename__ = "transactions"

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Dedupes retried client requests (mobile money callback replay, network
    # retry, double-click) — cf. cahier des charges §41/§45, Règle 12.
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
