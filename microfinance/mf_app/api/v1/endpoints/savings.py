from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import get_current_staff_user, get_tenant_db
from mf_app.models.staff_user import MFStaffUser
from mf_app.models.tenant.customer import Customer
from mf_app.models.tenant.ledger_entry import LedgerEntry
from mf_app.models.tenant.savings_account import SavingsAccount
from mf_app.models.tenant.savings_product import SavingsProduct
from mf_app.models.tenant.transaction import Transaction
from mf_app.schemas.customer import SavingsAccountOpen, SavingsTransactionRequest
from mf_app.schemas.savings import (
    SavingsAccountResponse,
    SavingsProductCreate,
    SavingsProductResponse,
    TransactionResponse,
)
from mf_app.services.rbac import require_permission
from mf_app.services.savings import (
    AccountNotActiveError,
    BelowMinimumOpeningBalanceError,
    CustomerNotVerifiedError,
    InsufficientFundsError,
    MissingIdempotencyKeyError,
    deposit,
    open_savings_account,
    withdraw,
)

products_router = APIRouter(
    prefix="/institutions/{institution_slug}/savings-products", tags=["savings"]
)
customer_accounts_router = APIRouter(
    prefix="/institutions/{institution_slug}/customers/{customer_id}/savings-accounts",
    tags=["savings"],
)
accounts_router = APIRouter(
    prefix="/institutions/{institution_slug}/savings-accounts", tags=["savings"]
)


@products_router.post(
    "", response_model=SavingsProductResponse, status_code=status.HTTP_201_CREATED
)
async def create_savings_product(
    payload: SavingsProductCreate,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> SavingsProduct:
    require_permission(staff.role, "savings_products:manage")
    existing = (
        await tenant_db.execute(select(SavingsProduct).where(SavingsProduct.code == payload.code))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Product code already in use")

    product = SavingsProduct(
        name=payload.name,
        code=payload.code,
        annual_interest_rate=payload.annual_interest_rate,
        min_opening_balance=payload.min_opening_balance,
    )
    tenant_db.add(product)
    await tenant_db.commit()
    await tenant_db.refresh(product)
    return product


@products_router.get("", response_model=list[SavingsProductResponse])
async def list_savings_products(
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> list[SavingsProduct]:
    require_permission(staff.role, "savings_products:read")
    result = await tenant_db.execute(select(SavingsProduct))
    return list(result.scalars().all())


@customer_accounts_router.post(
    "", response_model=SavingsAccountResponse, status_code=status.HTTP_201_CREATED
)
async def open_account(
    customer_id: uuid.UUID,
    payload: SavingsAccountOpen,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> SavingsAccount:
    require_permission(staff.role, "savings:transact")
    customer = await tenant_db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Customer not found")
    product = await tenant_db.get(SavingsProduct, payload.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Savings product not found")

    try:
        account = await open_savings_account(
            tenant_db,
            customer=customer,
            product=product,
            opening_deposit=payload.opening_deposit,
            idempotency_key=payload.idempotency_key,
        )
    except (
        CustomerNotVerifiedError,
        BelowMinimumOpeningBalanceError,
        MissingIdempotencyKeyError,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(account)
    return account


@customer_accounts_router.get("", response_model=list[SavingsAccountResponse])
async def list_customer_accounts(
    customer_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> list[SavingsAccount]:
    require_permission(staff.role, "savings:read")
    result = await tenant_db.execute(
        select(SavingsAccount).where(SavingsAccount.customer_id == customer_id)
    )
    return list(result.scalars().all())


@accounts_router.get("/{account_id}", response_model=SavingsAccountResponse)
async def get_account(
    account_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> SavingsAccount:
    require_permission(staff.role, "savings:read")
    account = await tenant_db.get(SavingsAccount, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Savings account not found")
    return account


@accounts_router.post("/{account_id}/deposit", response_model=TransactionResponse)
async def deposit_endpoint(
    account_id: uuid.UUID,
    payload: SavingsTransactionRequest,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Transaction:
    require_permission(staff.role, "savings:transact")
    account = await tenant_db.get(SavingsAccount, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Savings account not found")
    try:
        transaction = await deposit(
            tenant_db,
            account=account,
            amount=payload.amount,
            idempotency_key=payload.idempotency_key,
            description=payload.description,
        )
    except AccountNotActiveError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(transaction)
    return transaction


@accounts_router.post("/{account_id}/withdraw", response_model=TransactionResponse)
async def withdraw_endpoint(
    account_id: uuid.UUID,
    payload: SavingsTransactionRequest,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Transaction:
    require_permission(staff.role, "savings:transact")
    account = await tenant_db.get(SavingsAccount, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Savings account not found")
    try:
        transaction = await withdraw(
            tenant_db,
            account=account,
            amount=payload.amount,
            idempotency_key=payload.idempotency_key,
            description=payload.description,
        )
    except AccountNotActiveError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(transaction)
    return transaction


@accounts_router.get("/{account_id}/transactions", response_model=list[TransactionResponse])
async def list_account_transactions(
    account_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> list[Transaction]:
    require_permission(staff.role, "savings:read")
    result = await tenant_db.execute(
        select(Transaction)
        .join(LedgerEntry, LedgerEntry.transaction_id == Transaction.id)
        .where(LedgerEntry.account_type == "savings_account", LedgerEntry.account_id == account_id)
        .order_by(Transaction.created_at)
    )
    return list(result.scalars().unique().all())
