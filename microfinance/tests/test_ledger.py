"""Unit-level proof of the double-entry engine itself (docs/architecture/08
§8.7), against a real tenant database (SQLite in these tests, real Postgres in
the live-verified deployment) rather than through the HTTP API — this is what
lets a test assert directly on LedgerEntry rows and reconcile_balance.

Uses the two InternalAccounts every institution gets at onboarding time ("cash"
normal-debit, "interest_income" normal-credit) as the two legs of each test
transaction — a real bug in an earlier version of this file posted against a
fabricated, never-persisted `uuid.uuid4()` "savings_account" id, which the
ledger engine correctly rejected with "not found" once it started validating
that every account it's asked to touch actually exists.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from mf_app.models.tenant.internal_account import InternalAccount
from mf_app.models.tenant.ledger_entry import LedgerDirection
from mf_app.services.ledger import LedgerLine, post_transaction, reconcile_balance


async def _get_accounts(db):
    cash = (
        await db.execute(select(InternalAccount).where(InternalAccount.name == "cash"))
    ).scalar_one()
    interest_income = (
        await db.execute(select(InternalAccount).where(InternalAccount.name == "interest_income"))
    ).scalar_one()
    return cash, interest_income


async def test_balanced_transaction_updates_balances_correctly(onboarded_institution):
    async with onboarded_institution["tenant_session_factory"]() as db:
        cash, interest_income = await _get_accounts(db)

        await post_transaction(
            db,
            type="deposit",
            idempotency_key="dep-1",
            lines=[
                LedgerLine("internal_account", cash.id, LedgerDirection.DEBIT, Decimal("100.00")),
                LedgerLine(
                    "internal_account",
                    interest_income.id,
                    LedgerDirection.CREDIT,
                    Decimal("100.00"),
                ),
            ],
        )
        await db.commit()

        await db.refresh(cash)
        await db.refresh(interest_income)
        assert cash.balance_cached == Decimal("100.00")
        assert interest_income.balance_cached == Decimal("100.00")


async def test_unbalanced_transaction_is_rejected(onboarded_institution):
    async with onboarded_institution["tenant_session_factory"]() as db:
        cash, interest_income = await _get_accounts(db)

        with pytest.raises(AssertionError):
            await post_transaction(
                db,
                type="deposit",
                idempotency_key="unbalanced-1",
                lines=[
                    LedgerLine(
                        "internal_account", cash.id, LedgerDirection.DEBIT, Decimal("100.00")
                    ),
                    LedgerLine(
                        "internal_account",
                        interest_income.id,
                        LedgerDirection.CREDIT,
                        Decimal("50.00"),
                    ),
                ],
            )


async def test_posting_against_a_nonexistent_account_is_rejected(onboarded_institution):
    import uuid

    async with onboarded_institution["tenant_session_factory"]() as db:
        cash, _ = await _get_accounts(db)

        with pytest.raises(ValueError, match="not found"):
            await post_transaction(
                db,
                type="deposit",
                idempotency_key="ghost-account",
                lines=[
                    LedgerLine(
                        "internal_account", cash.id, LedgerDirection.DEBIT, Decimal("10.00")
                    ),
                    LedgerLine(
                        "savings_account", uuid.uuid4(), LedgerDirection.CREDIT, Decimal("10.00")
                    ),
                ],
            )


async def test_idempotent_replay_does_not_double_post(onboarded_institution):
    async with onboarded_institution["tenant_session_factory"]() as db:
        cash, interest_income = await _get_accounts(db)
        lines = [
            LedgerLine("internal_account", cash.id, LedgerDirection.DEBIT, Decimal("30.00")),
            LedgerLine(
                "internal_account", interest_income.id, LedgerDirection.CREDIT, Decimal("30.00")
            ),
        ]

        first = await post_transaction(db, type="deposit", idempotency_key="replay-1", lines=lines)
        await db.commit()
        second = await post_transaction(db, type="deposit", idempotency_key="replay-1", lines=lines)
        await db.commit()

        assert first.id == second.id
        await db.refresh(cash)
        assert cash.balance_cached == Decimal("30.00")  # not 60 — the replay was a no-op


async def test_reconcile_balance_matches_cache_after_several_transactions(onboarded_institution):
    async with onboarded_institution["tenant_session_factory"]() as db:
        cash, interest_income = await _get_accounts(db)

        for i, amount in enumerate([Decimal("100.00"), Decimal("50.00"), Decimal("-20.00")]):
            direction_credit_side = LedgerDirection.CREDIT if amount > 0 else LedgerDirection.DEBIT
            direction_cash = LedgerDirection.DEBIT if amount > 0 else LedgerDirection.CREDIT
            await post_transaction(
                db,
                type="deposit" if amount > 0 else "withdrawal",
                idempotency_key=f"seq-{i}",
                lines=[
                    LedgerLine("internal_account", cash.id, direction_cash, abs(amount)),
                    LedgerLine(
                        "internal_account", interest_income.id, direction_credit_side, abs(amount)
                    ),
                ],
            )
        await db.commit()

        reconciled = await reconcile_balance(
            db, account_type="internal_account", account_id=interest_income.id
        )
        assert reconciled == Decimal("130.00")  # 100 + 50 - 20
