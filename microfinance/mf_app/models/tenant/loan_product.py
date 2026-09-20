from __future__ import annotations

import enum

from sqlalchemy import Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin


class AmortizationMethod(str, enum.Enum):
    # Equal installments; interest computed on the declining principal balance
    # each period (§8.8's formula: installment = P*r/(1-(1+r)^-n)).
    DECLINING_BALANCE = "declining_balance"
    # Interest is a fixed fraction of the ORIGINAL principal every period,
    # principal repaid in equal slices — simpler, costs the borrower more
    # total interest than declining balance for the same nominal rate.
    FLAT = "flat"


class LoanProduct(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "loan_products"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    amortization_method: Mapped[AmortizationMethod] = mapped_column(
        Enum(AmortizationMethod, native_enum=False, length=20), nullable=False
    )
    # Periodic (not annual) rate, matching the installment period (assumed
    # monthly at this stage — cf. §8.8) — e.g. 0.02 for 2%/month.
    periodic_interest_rate: Mapped[Numeric] = mapped_column(Numeric(8, 6), nullable=False)
    min_principal: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    max_principal: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    min_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    max_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
