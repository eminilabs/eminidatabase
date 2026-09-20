"""Pure function tests for the repayment schedule formulas (docs/architecture/08
§8.8) — no DB, no institution, just the math. Invariant-based rather than
hardcoded expected numbers: the formulas' whole point is that they're
deterministic and exact (cahier des charges §41/§45), which is exactly what
"principal_due sums to the original principal, to the cent" proves without
requiring a fragile hand-computed reference value.
"""

import datetime as dt
from decimal import Decimal

from mf_app.models.tenant.loan_product import AmortizationMethod
from mf_app.services.amortization import add_months, generate_repayment_schedule


def test_add_months_handles_month_end_clamping():
    assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert add_months(dt.date(2026, 1, 15), 13) == dt.date(2027, 2, 15)


def test_declining_balance_principal_sums_to_original_exactly():
    lines = generate_repayment_schedule(
        principal=Decimal("1200.00"),
        periodic_rate=Decimal("0.02"),
        term_months=12,
        method=AmortizationMethod.DECLINING_BALANCE,
        start_date=dt.date(2026, 1, 1),
    )
    assert len(lines) == 12
    assert sum((line.principal_due for line in lines), Decimal("0")) == Decimal("1200.00")
    # Declining balance means declining interest — each period's interest must
    # not increase versus the previous one.
    for previous, current in zip(lines, lines[1:], strict=False):
        assert current.interest_due <= previous.interest_due
    for i, line in enumerate(lines, start=1):
        assert line.installment_number == i
        assert line.due_date == add_months(dt.date(2026, 1, 1), i)


def test_flat_principal_sums_to_original_exactly_and_interest_is_constant():
    lines = generate_repayment_schedule(
        principal=Decimal("1000.00"),
        periodic_rate=Decimal("0.015"),
        term_months=10,
        method=AmortizationMethod.FLAT,
        start_date=dt.date(2026, 1, 1),
    )
    assert len(lines) == 10
    assert sum((line.principal_due for line in lines), Decimal("0")) == Decimal("1000.00")
    interest_values = {line.interest_due for line in lines}
    assert len(interest_values) == 1  # constant every period, by definition of "flat"


def test_zero_rate_schedule_has_no_interest():
    lines = generate_repayment_schedule(
        principal=Decimal("300.00"),
        periodic_rate=Decimal("0"),
        term_months=3,
        method=AmortizationMethod.DECLINING_BALANCE,
        start_date=dt.date(2026, 1, 1),
    )
    assert all(line.interest_due == Decimal("0") for line in lines)
    assert sum((line.principal_due for line in lines), Decimal("0")) == Decimal("300.00")


def test_rounding_remainder_is_absorbed_by_last_installment():
    # 100 / 3 does not divide evenly — proves the last line, not a silent
    # cross-the-board rounding error, is what makes the total exact.
    lines = generate_repayment_schedule(
        principal=Decimal("100.00"),
        periodic_rate=Decimal("0"),
        term_months=3,
        method=AmortizationMethod.FLAT,
        start_date=dt.date(2026, 1, 1),
    )
    assert [line.principal_due for line in lines] == [
        Decimal("33.33"),
        Decimal("33.33"),
        Decimal("33.34"),
    ]
