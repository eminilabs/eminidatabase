from __future__ import annotations

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin


class SavingsProduct(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "savings_products"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    # Annual rate, informational at this stage — interest accrual/capitalization
    # is not yet automated (no scheduler job posts interest transactions); left
    # for a future increment rather than half-built here.
    annual_interest_rate: Mapped[Numeric] = mapped_column(Numeric(6, 4), default=0, nullable=False)
    min_opening_balance: Mapped[Numeric] = mapped_column(
        Numeric(18, 2), default=0, nullable=False
    )
