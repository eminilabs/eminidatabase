from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class LoanStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    # §8.6 lists disbursed and active as separate states; merged here since
    # disbursement immediately starts the repayment schedule — a lingering
    # "disbursed but not yet active" state has no distinct behavior to encode,
    # documented simplification rather than a half-built extra state.
    ACTIVE = "active"
    CLOSED = "closed"
    DEFAULTED = "defaulted"


class Loan(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "loans"

    customer_id: Mapped[str] = mapped_column(GUID(), ForeignKey("customers.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("loan_products.id"), nullable=False
    )
    principal: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus, native_enum=False, length=20), default=LoanStatus.DRAFT, nullable=False
    )
    # Opaque link to the approving MFStaffUser (control DB) — no FK across
    # databases, same pattern as MFStaffUser.tenant_agent_id (cf. §8.6).
    approved_by_staff_id: Mapped[str | None] = mapped_column(GUID(), nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    disbursed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Every ledger entry for this loan (disbursement, repayments) posts against
    # this InternalAccount-like balance — the loan IS the account here (an
    # asset from the institution's books: money owed BY the customer).
    outstanding_principal: Mapped[Numeric] = mapped_column(
        Numeric(18, 2), default=0, nullable=False
    )
