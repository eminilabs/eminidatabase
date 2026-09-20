"""Loan lifecycle: draft → pending_approval → approved → active (disbursed) →
closed/rejected (cf. docs/architecture/08 §8.6). Every state transition is one
function here — no endpoint ever flips `Loan.status` directly. Money movement
(disbursement, repayment) always goes through mf_app/services/ledger.py.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.timeutil import utcnow
from mf_app.models.tenant.customer import Customer, KYCStatus
from mf_app.models.tenant.ledger_entry import LedgerDirection
from mf_app.models.tenant.loan import Loan, LoanStatus
from mf_app.models.tenant.loan_product import LoanProduct
from mf_app.models.tenant.repayment_schedule import (
    RepaymentLineStatus,
    RepaymentSchedule,
    RepaymentScheduleLine,
)
from mf_app.services.amortization import generate_repayment_schedule
from mf_app.services.ledger import LedgerLine, post_transaction
from mf_app.services.savings import get_cash_account


class CustomerNotVerifiedError(Exception):
    pass


class InvalidLoanAmountError(Exception):
    pass


class InvalidLoanTermError(Exception):
    pass


class InvalidLoanStateError(Exception):
    pass


class OverpaymentError(Exception):
    pass


async def get_interest_income_account(db: AsyncSession):
    from mf_app.models.tenant.internal_account import InternalAccount

    account = (
        await db.execute(
            select(InternalAccount).where(InternalAccount.name == "interest_income")
        )
    ).scalar_one_or_none()
    if account is None:
        raise RuntimeError(
            "Institution has no 'interest_income' InternalAccount — onboarding is incomplete"
        )
    return account


async def create_loan(
    db: AsyncSession,
    *,
    customer: Customer,
    product: LoanProduct,
    principal: Decimal,
    term_months: int,
) -> Loan:
    if customer.kyc_status != KYCStatus.VERIFIED:
        raise CustomerNotVerifiedError(
            f"Customer {customer.id} is not KYC-verified (status={customer.kyc_status.value})"
        )
    if not (product.min_principal <= principal <= product.max_principal):
        raise InvalidLoanAmountError(
            f"Principal {principal} is outside product {product.code}'s allowed range "
            f"[{product.min_principal}, {product.max_principal}]"
        )
    if not (product.min_term_months <= term_months <= product.max_term_months):
        raise InvalidLoanTermError(
            f"Term {term_months} months is outside product {product.code}'s allowed range "
            f"[{product.min_term_months}, {product.max_term_months}]"
        )

    loan = Loan(
        customer_id=customer.id,
        product_id=product.id,
        principal=principal,
        term_months=term_months,
    )
    db.add(loan)
    await db.flush()
    return loan


def _require_status(loan: Loan, expected: LoanStatus) -> None:
    if loan.status != expected:
        raise InvalidLoanStateError(
            f"Loan {loan.id} is {loan.status.value}, expected {expected.value}"
        )


async def submit_for_approval(db: AsyncSession, *, loan: Loan) -> Loan:
    _require_status(loan, LoanStatus.DRAFT)
    loan.status = LoanStatus.PENDING_APPROVAL
    await db.flush()
    return loan


async def approve_loan(db: AsyncSession, *, loan: Loan, staff_id: uuid.UUID) -> Loan:
    _require_status(loan, LoanStatus.PENDING_APPROVAL)
    loan.status = LoanStatus.APPROVED
    loan.approved_by_staff_id = staff_id
    loan.approved_at = utcnow()
    await db.flush()
    return loan


async def reject_loan(db: AsyncSession, *, loan: Loan, staff_id: uuid.UUID, reason: str) -> Loan:
    _require_status(loan, LoanStatus.PENDING_APPROVAL)
    loan.status = LoanStatus.REJECTED
    loan.approved_by_staff_id = staff_id
    loan.rejection_reason = reason
    await db.flush()
    return loan


async def disburse_loan(
    db: AsyncSession,
    *,
    loan: Loan,
    product: LoanProduct,
    idempotency_key: str,
    disbursement_date: date | None = None,
) -> Loan:
    _require_status(loan, LoanStatus.APPROVED)
    disbursement_date = disbursement_date or utcnow().date()

    schedule_lines = generate_repayment_schedule(
        principal=loan.principal,
        periodic_rate=product.periodic_interest_rate,
        term_months=loan.term_months,
        method=product.amortization_method,
        start_date=disbursement_date,
    )
    schedule = RepaymentSchedule(loan_id=loan.id, version=1, is_active=True)
    db.add(schedule)
    await db.flush()
    for line in schedule_lines:
        db.add(
            RepaymentScheduleLine(
                schedule_id=schedule.id,
                installment_number=line.installment_number,
                due_date=line.due_date,
                principal_due=line.principal_due,
                interest_due=line.interest_due,
            )
        )

    cash = await get_cash_account(db)
    await post_transaction(
        db,
        type="disbursement",
        idempotency_key=idempotency_key,
        description=f"Disbursement of loan {loan.id}",
        lines=[
            LedgerLine("loan", loan.id, LedgerDirection.DEBIT, loan.principal),
            LedgerLine("internal_account", cash.id, LedgerDirection.CREDIT, loan.principal),
        ],
    )

    loan.status = LoanStatus.ACTIVE
    loan.disbursed_at = utcnow()
    await db.flush()
    return loan


async def repay_installment(
    db: AsyncSession, *, loan: Loan, amount: Decimal, idempotency_key: str
) -> tuple:
    """Applies `amount` to the oldest unpaid installment of the loan's active
    schedule. Deliberately scoped to one installment per payment — splitting a
    single payment across multiple installments, or accepting prepayment
    beyond what's currently due, is a real feature but not required by this
    phase's exit criterion and is left as a documented future increment rather
    than half-built here."""
    _require_status(loan, LoanStatus.ACTIVE)

    schedule = (
        await db.execute(
            select(RepaymentSchedule).where(
                RepaymentSchedule.loan_id == loan.id, RepaymentSchedule.is_active.is_(True)
            )
        )
    ).scalar_one()
    line = (
        await db.execute(
            select(RepaymentScheduleLine)
            .where(
                RepaymentScheduleLine.schedule_id == schedule.id,
                RepaymentScheduleLine.status == RepaymentLineStatus.PENDING,
            )
            .order_by(RepaymentScheduleLine.installment_number)
            .limit(1)
        )
    ).scalar_one_or_none()
    if line is None:
        raise InvalidLoanStateError(f"Loan {loan.id} has no pending installment")

    interest_remaining = line.interest_due - line.interest_paid
    principal_remaining = line.principal_due - line.principal_paid
    total_remaining = interest_remaining + principal_remaining
    if amount > total_remaining:
        raise OverpaymentError(
            f"Amount {amount} exceeds the {total_remaining} still due on installment "
            f"{line.installment_number}"
        )

    # Interest is settled before principal — standard convention, and it's
    # also what the ledger split below needs to know how to book.
    interest_portion = min(amount, interest_remaining)
    principal_portion = amount - interest_portion

    line.interest_paid += interest_portion
    line.principal_paid += principal_portion
    if line.principal_paid == line.principal_due and line.interest_paid == line.interest_due:
        line.status = RepaymentLineStatus.PAID

    cash = await get_cash_account(db)
    interest_income = await get_interest_income_account(db)
    lines = [LedgerLine("internal_account", cash.id, LedgerDirection.DEBIT, amount)]
    if principal_portion > 0:
        lines.append(LedgerLine("loan", loan.id, LedgerDirection.CREDIT, principal_portion))
    if interest_portion > 0:
        lines.append(
            LedgerLine(
                "internal_account", interest_income.id, LedgerDirection.CREDIT, interest_portion
            )
        )
    transaction = await post_transaction(
        db,
        type="repayment",
        idempotency_key=idempotency_key,
        description=f"Repayment of loan {loan.id} installment {line.installment_number}",
        lines=lines,
    )

    remaining_lines = (
        await db.execute(
            select(RepaymentScheduleLine).where(
                RepaymentScheduleLine.schedule_id == schedule.id,
                RepaymentScheduleLine.status == RepaymentLineStatus.PENDING,
            )
        )
    ).scalars().all()
    if not remaining_lines:
        loan.status = LoanStatus.CLOSED
        loan.closed_at = utcnow()

    await db.flush()
    return transaction, line
