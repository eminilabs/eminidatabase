"""The double-entry ledger engine (docs/architecture/08 §8.7) — the ONLY code
allowed to write LedgerEntry rows. No endpoint, no other service function, ever
inserts one directly; savings/loan operations build LedgerLines and call
post_transaction(), nothing more.

Accounting convention: every account has a "normal balance side". Asset
accounts (InternalAccount "cash") are normal-DEBIT — a debit increases their
balance. Liability accounts (a customer's SavingsAccount, which is money the
institution owes the customer) are normal-CREDIT — a credit increases their
balance. A deposit of A is booked as Debit cash A / Credit savings A (cash
asset up, customer's balance up); a withdrawal is the mirror image. Getting
this backwards would make deposits decrease a customer's displayed balance, so
it is centralized here instead of re-derived at every call site.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.models.tenant.internal_account import InternalAccount
from mf_app.models.tenant.ledger_entry import LedgerDirection, LedgerEntry
from mf_app.models.tenant.loan import Loan
from mf_app.models.tenant.savings_account import SavingsAccount
from mf_app.models.tenant.transaction import Transaction

# Fixed for the account types with only one possible kind (a savings account is
# always a liability, a loan is always an asset from the institution's books);
# InternalAccount stores its own side per row since Phase 9.4's chart of
# accounts will add accounts of different kinds (asset cash, revenue interest
# income, ...) that can't be inferred from the type alone.
_FIXED_NORMAL_SIDE = {"savings_account": "credit", "loan": "debit"}

# The balance column name differs per account type ("outstanding_principal"
# reads far better on a Loan than the generic "balance_cached") — the engine
# stays generic via this lookup instead of hardcoding one field name.
_BALANCE_FIELD = {
    "internal_account": "balance_cached",
    "savings_account": "balance_cached",
    "loan": "outstanding_principal",
}


@dataclass(frozen=True)
class LedgerLine:
    account_type: str
    account_id: uuid.UUID
    direction: LedgerDirection
    amount: Decimal


async def _get_account(db: AsyncSession, account_type: str, account_id: uuid.UUID):
    if account_type == "internal_account":
        account = await db.get(InternalAccount, account_id)
    elif account_type == "savings_account":
        account = await db.get(SavingsAccount, account_id)
    elif account_type == "loan":
        account = await db.get(Loan, account_id)
    else:
        raise ValueError(f"Unknown ledger account_type {account_type!r}")
    if account is None:
        raise ValueError(f"{account_type} {account_id} not found")
    return account


def _normal_side(account_type: str, account) -> str:
    return _FIXED_NORMAL_SIDE.get(account_type) or account.normal_balance_side


async def post_transaction(
    db: AsyncSession,
    *,
    type: str,
    idempotency_key: str,
    lines: list[LedgerLine],
    description: str | None = None,
) -> Transaction:
    existing = (
        await db.execute(select(Transaction).where(Transaction.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    total_debits = sum(
        (line.amount for line in lines if line.direction == LedgerDirection.DEBIT), Decimal("0")
    )
    total_credits = sum(
        (line.amount for line in lines if line.direction == LedgerDirection.CREDIT), Decimal("0")
    )
    if total_debits != total_credits:
        # A bug, never a business-input error — callers build both sides of
        # every transaction themselves (cf. mf_app/services/savings.py).
        raise AssertionError(
            f"Unbalanced ledger transaction: debits={total_debits} credits={total_credits}"
        )

    transaction = Transaction(
        type=type,
        amount=total_debits,
        description=description,
        idempotency_key=idempotency_key,
    )
    db.add(transaction)
    await db.flush()

    for line in lines:
        account = await _get_account(db, line.account_type, line.account_id)
        db.add(
            LedgerEntry(
                transaction_id=transaction.id,
                account_type=line.account_type,
                account_id=line.account_id,
                direction=line.direction,
                amount=line.amount,
            )
        )
        sign = 1 if line.direction.value == _normal_side(line.account_type, account) else -1
        field = _BALANCE_FIELD[line.account_type]
        setattr(account, field, getattr(account, field) + sign * line.amount)

    await db.flush()
    return transaction


async def reconcile_balance(
    db: AsyncSession, *, account_type: str, account_id: uuid.UUID
) -> Decimal:
    """Recomputes a balance purely from LedgerEntry rows — used to prove
    balance_cached never drifts from the ledger, the actual source of truth."""
    account = await _get_account(db, account_type, account_id)
    normal_side = _normal_side(account_type, account)
    entries = (
        await db.execute(
            select(LedgerEntry).where(
                LedgerEntry.account_type == account_type, LedgerEntry.account_id == account_id
            )
        )
    ).scalars().all()
    total = Decimal("0")
    for entry in entries:
        sign = 1 if entry.direction.value == normal_side else -1
        total += sign * entry.amount
    return total
