from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class RepaymentLineStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"


class RepaymentSchedule(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    """One version of a loan's schedule (§8.6/§8.8) — a restructuring creates a
    NEW row with a higher `version` rather than mutating this one, so the
    original schedule stays available for audit. Only one schedule per loan
    has `is_active=True` at a time."""

    __tablename__ = "repayment_schedules"

    loan_id: Mapped[str] = mapped_column(GUID(), ForeignKey("loans.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RepaymentScheduleLine(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "repayment_schedule_lines"

    schedule_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("repayment_schedules.id"), nullable=False
    )
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    principal_due: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    interest_due: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    # Column exists per §8.6 but no penalty calculation logic runs yet (no
    # scheduler checks for overdue lines) — left as a documented future
    # increment rather than half-implemented here.
    penalty_due: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    principal_paid: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    interest_paid: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    status: Mapped[RepaymentLineStatus] = mapped_column(
        Enum(RepaymentLineStatus, native_enum=False, length=20),
        default=RepaymentLineStatus.PENDING,
        nullable=False,
    )
