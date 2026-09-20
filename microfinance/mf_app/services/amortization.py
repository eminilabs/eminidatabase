"""Repayment schedule generation (docs/architecture/08 §8.8) — a pure function,
deliberately separate from any DB/ledger code so the formula itself is trivial
to unit-test in isolation. Called once, at disbursement; the result is
persisted as immutable RepaymentScheduleLine rows and never recomputed
silently (cf. §8.8 — a restructuring creates a new schedule version instead).
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from mf_app.models.tenant.loan_product import AmortizationMethod

_CENTS = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ScheduleLine:
    installment_number: int
    due_date: dt.date
    principal_due: Decimal
    interest_due: Decimal


def add_months(base: dt.date, months: int) -> dt.date:
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def generate_repayment_schedule(
    *,
    principal: Decimal,
    periodic_rate: Decimal,
    term_months: int,
    method: AmortizationMethod,
    start_date: dt.date,
) -> list[ScheduleLine]:
    """Both methods make the LAST installment absorb any rounding remainder so
    the sum of principal_due across all lines is always exactly `principal` —
    a deterministic, traceable total is the whole point (cahier des charges
    §41/§45), not an approximation that drifts by a few cents."""
    if method == AmortizationMethod.FLAT:
        return _flat_schedule(principal, periodic_rate, term_months, start_date)
    return _declining_balance_schedule(principal, periodic_rate, term_months, start_date)


def _flat_schedule(
    principal: Decimal, periodic_rate: Decimal, term_months: int, start_date: dt.date
) -> list[ScheduleLine]:
    principal_per_period = _round(principal / term_months)
    interest_per_period = _round(principal * periodic_rate)

    lines = []
    allocated = Decimal("0")
    for i in range(1, term_months + 1):
        if i == term_months:
            principal_due = principal - allocated
        else:
            principal_due = principal_per_period
            allocated += principal_due
        lines.append(
            ScheduleLine(i, add_months(start_date, i), principal_due, interest_per_period)
        )
    return lines


def _declining_balance_schedule(
    principal: Decimal, periodic_rate: Decimal, term_months: int, start_date: dt.date
) -> list[ScheduleLine]:
    if periodic_rate == 0:
        installment = _round(principal / term_months)
    else:
        factor = 1 - (1 + periodic_rate) ** (-term_months)
        installment = _round(principal * periodic_rate / factor)

    remaining = principal
    lines = []
    for i in range(1, term_months + 1):
        interest_due = _round(remaining * periodic_rate)
        if i == term_months:
            principal_due = remaining
        else:
            principal_due = _round(installment - interest_due)
        lines.append(ScheduleLine(i, add_months(start_date, i), principal_due, interest_due))
        remaining -= principal_due
    return lines
