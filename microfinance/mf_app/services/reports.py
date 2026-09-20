"""Accounting reports (docs/architecture/08 §8.10, Phase 9.4) — read-only views
over the ledger's own accounts, not a separate bookkeeping system. The trial
balance in particular is the audit proof that the ledger engine
(mf_app/services/ledger.py) is doing its job: every transaction it ever posts
is balanced by construction, so summing every account's balance by its normal
side must always land on `balanced=True` — if it doesn't, that's a real bug in
the engine, not a data-entry error to fix by hand.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.models.tenant.internal_account import InternalAccount
from mf_app.models.tenant.loan import Loan, LoanStatus
from mf_app.models.tenant.savings_account import SavingsAccount


async def get_trial_balance(db: AsyncSession) -> dict:
    internal_accounts = (await db.execute(select(InternalAccount))).scalars().all()
    savings_total = (
        await db.execute(select(func.coalesce(func.sum(SavingsAccount.balance_cached), 0)))
    ).scalar_one()
    loans_total = (
        await db.execute(select(func.coalesce(func.sum(Loan.outstanding_principal), 0)))
    ).scalar_one()

    lines = []
    debit_total = Decimal("0")
    credit_total = Decimal("0")

    for account in internal_accounts:
        lines.append(
            {
                "account_type": "internal_account",
                "account_id": account.id,
                "label": account.name,
                "normal_side": account.normal_balance_side,
                "balance": account.balance_cached,
            }
        )
        if account.normal_balance_side == "debit":
            debit_total += account.balance_cached
        else:
            credit_total += account.balance_cached

    savings_total = Decimal(savings_total)
    lines.append(
        {
            "account_type": "savings_accounts_total",
            "account_id": None,
            "label": "Customer savings (liability)",
            "normal_side": "credit",
            "balance": savings_total,
        }
    )
    credit_total += savings_total

    loans_total = Decimal(loans_total)
    lines.append(
        {
            "account_type": "loans_total",
            "account_id": None,
            "label": "Loans outstanding (asset)",
            "normal_side": "debit",
            "balance": loans_total,
        }
    )
    debit_total += loans_total

    return {
        "lines": lines,
        "total_debit_side": debit_total,
        "total_credit_side": credit_total,
        "balanced": debit_total == credit_total,
    }


async def get_loan_portfolio(db: AsyncSession) -> dict:
    active_or_closed = select(Loan).where(Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.CLOSED]))
    loans = (await db.execute(active_or_closed)).scalars().all()
    active_loans = [loan for loan in loans if loan.status == LoanStatus.ACTIVE]
    return {
        "active_loan_count": len(active_loans),
        "total_principal_disbursed": sum((loan.principal for loan in loans), Decimal("0")),
        "total_outstanding_principal": sum(
            (loan.outstanding_principal for loan in active_loans), Decimal("0")
        ),
    }
