"""Savings account operations — no balance logic of its own, everything goes
through mf_app/services/ledger.py::post_transaction (cf. docs/architecture/08
§8.7)."""

from __future__ import annotations

import secrets
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.models.tenant.customer import Customer, KYCStatus
from mf_app.models.tenant.internal_account import InternalAccount
from mf_app.models.tenant.ledger_entry import LedgerDirection
from mf_app.models.tenant.savings_account import SavingsAccount, SavingsAccountStatus
from mf_app.models.tenant.savings_product import SavingsProduct
from mf_app.services.ledger import LedgerLine, post_transaction


class InsufficientFundsError(Exception):
    pass


class AccountNotActiveError(Exception):
    pass


class CustomerNotVerifiedError(Exception):
    pass


class BelowMinimumOpeningBalanceError(Exception):
    pass


class MissingIdempotencyKeyError(Exception):
    pass


def generate_account_number() -> str:
    return f"SA-{secrets.token_hex(5).upper()}"


async def get_cash_account(db: AsyncSession) -> InternalAccount:
    account = (
        await db.execute(select(InternalAccount).where(InternalAccount.name == "cash"))
    ).scalar_one_or_none()
    if account is None:
        raise RuntimeError("Institution has no 'cash' InternalAccount — onboarding is incomplete")
    return account


async def open_savings_account(
    db: AsyncSession,
    *,
    customer: Customer,
    product: SavingsProduct,
    opening_deposit: Decimal,
    idempotency_key: str | None,
) -> SavingsAccount:
    if customer.kyc_status != KYCStatus.VERIFIED:
        raise CustomerNotVerifiedError(
            f"Customer {customer.id} is not KYC-verified (status={customer.kyc_status.value})"
        )
    if opening_deposit < product.min_opening_balance:
        raise BelowMinimumOpeningBalanceError(
            f"Opening deposit {opening_deposit} is below product {product.code}'s "
            f"minimum of {product.min_opening_balance}"
        )
    account = SavingsAccount(
        customer_id=customer.id,
        product_id=product.id,
        account_number=generate_account_number(),
    )
    db.add(account)
    await db.flush()

    if opening_deposit > 0:
        if not idempotency_key:
            raise MissingIdempotencyKeyError("idempotency_key is required for an opening deposit")
        await deposit(
            db,
            account=account,
            amount=opening_deposit,
            idempotency_key=idempotency_key,
            description="Opening deposit",
        )
    return account


async def deposit(
    db: AsyncSession,
    *,
    account: SavingsAccount,
    amount: Decimal,
    idempotency_key: str,
    description: str | None = None,
):
    if account.status != SavingsAccountStatus.ACTIVE:
        raise AccountNotActiveError(f"Savings account {account.id} is not active")
    cash = await get_cash_account(db)
    return await post_transaction(
        db,
        type="deposit",
        idempotency_key=idempotency_key,
        description=description,
        lines=[
            LedgerLine("internal_account", cash.id, LedgerDirection.DEBIT, amount),
            LedgerLine("savings_account", account.id, LedgerDirection.CREDIT, amount),
        ],
    )


async def withdraw(
    db: AsyncSession,
    *,
    account: SavingsAccount,
    amount: Decimal,
    idempotency_key: str,
    description: str | None = None,
):
    if account.status != SavingsAccountStatus.ACTIVE:
        raise AccountNotActiveError(f"Savings account {account.id} is not active")
    if account.balance_cached < amount:
        raise InsufficientFundsError(
            f"Balance {account.balance_cached} is less than requested withdrawal {amount}"
        )
    cash = await get_cash_account(db)
    return await post_transaction(
        db,
        type="withdrawal",
        idempotency_key=idempotency_key,
        description=description,
        lines=[
            LedgerLine("savings_account", account.id, LedgerDirection.DEBIT, amount),
            LedgerLine("internal_account", cash.id, LedgerDirection.CREDIT, amount),
        ],
    )
