from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import get_current_staff_user, get_tenant_db
from mf_app.models.staff_user import MFStaffUser
from mf_app.models.tenant.customer import Customer
from mf_app.models.tenant.loan import Loan
from mf_app.models.tenant.loan_product import LoanProduct
from mf_app.models.tenant.repayment_schedule import RepaymentSchedule, RepaymentScheduleLine
from mf_app.schemas.loan import (
    LoanCreate,
    LoanDisburseRequest,
    LoanProductCreate,
    LoanProductResponse,
    LoanRejectRequest,
    LoanRepayRequest,
    LoanResponse,
    RepaymentScheduleLineResponse,
)
from mf_app.services.loans import (
    CustomerNotVerifiedError,
    InvalidLoanAmountError,
    InvalidLoanStateError,
    InvalidLoanTermError,
    OverpaymentError,
    approve_loan,
    create_loan,
    disburse_loan,
    reject_loan,
    repay_installment,
    submit_for_approval,
)
from mf_app.services.rbac import require_permission

products_router = APIRouter(
    prefix="/institutions/{institution_slug}/loan-products", tags=["loans"]
)
router = APIRouter(prefix="/institutions/{institution_slug}/loans", tags=["loans"])

_BUSINESS_ERRORS = (
    CustomerNotVerifiedError,
    InvalidLoanAmountError,
    InvalidLoanTermError,
    InvalidLoanStateError,
    OverpaymentError,
)


@products_router.post(
    "", response_model=LoanProductResponse, status_code=status.HTTP_201_CREATED
)
async def create_loan_product(
    payload: LoanProductCreate,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> LoanProduct:
    require_permission(staff.role, "loan_products:manage")
    existing = (
        await tenant_db.execute(select(LoanProduct).where(LoanProduct.code == payload.code))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Product code already in use")

    product = LoanProduct(**payload.model_dump())
    tenant_db.add(product)
    await tenant_db.commit()
    await tenant_db.refresh(product)
    return product


@products_router.get("", response_model=list[LoanProductResponse])
async def list_loan_products(
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> list[LoanProduct]:
    require_permission(staff.role, "loan_products:read")
    result = await tenant_db.execute(select(LoanProduct))
    return list(result.scalars().all())


@router.post("", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
async def create_loan_application(
    payload: LoanCreate,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Loan:
    require_permission(staff.role, "loans:manage")
    customer = await tenant_db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Customer not found")
    product = await tenant_db.get(LoanProduct, payload.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan product not found")

    try:
        loan = await create_loan(
            tenant_db,
            customer=customer,
            product=product,
            principal=payload.principal,
            term_months=payload.term_months,
        )
    except _BUSINESS_ERRORS as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(loan)
    return loan


@router.get("/{loan_id}", response_model=LoanResponse)
async def get_loan(
    loan_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Loan:
    require_permission(staff.role, "loans:read")
    loan = await tenant_db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    return loan


@router.post("/{loan_id}/submit", response_model=LoanResponse)
async def submit_loan(
    loan_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Loan:
    require_permission(staff.role, "loans:manage")
    loan = await tenant_db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    try:
        await submit_for_approval(tenant_db, loan=loan)
    except _BUSINESS_ERRORS as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(loan)
    return loan


@router.post("/{loan_id}/approve", response_model=LoanResponse)
async def approve_loan_endpoint(
    loan_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Loan:
    require_permission(staff.role, "loans:approve")
    loan = await tenant_db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    try:
        await approve_loan(tenant_db, loan=loan, staff_id=staff.id)
    except _BUSINESS_ERRORS as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(loan)
    return loan


@router.post("/{loan_id}/reject", response_model=LoanResponse)
async def reject_loan_endpoint(
    loan_id: uuid.UUID,
    payload: LoanRejectRequest,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Loan:
    require_permission(staff.role, "loans:approve")
    loan = await tenant_db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    try:
        await reject_loan(tenant_db, loan=loan, staff_id=staff.id, reason=payload.reason)
    except _BUSINESS_ERRORS as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(loan)
    return loan


@router.post("/{loan_id}/disburse", response_model=LoanResponse)
async def disburse_loan_endpoint(
    loan_id: uuid.UUID,
    payload: LoanDisburseRequest,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Loan:
    require_permission(staff.role, "loans:disburse")
    loan = await tenant_db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    product = await tenant_db.get(LoanProduct, loan.product_id)
    try:
        await disburse_loan(
            tenant_db, loan=loan, product=product, idempotency_key=payload.idempotency_key
        )
    except _BUSINESS_ERRORS as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(loan)
    return loan


@router.post("/{loan_id}/repay", response_model=LoanResponse)
async def repay_loan_endpoint(
    loan_id: uuid.UUID,
    payload: LoanRepayRequest,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Loan:
    require_permission(staff.role, "loans:repay")
    loan = await tenant_db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    try:
        await repay_installment(
            tenant_db, loan=loan, amount=payload.amount, idempotency_key=payload.idempotency_key
        )
    except _BUSINESS_ERRORS as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await tenant_db.commit()
    await tenant_db.refresh(loan)
    return loan


@router.get("/{loan_id}/schedule", response_model=list[RepaymentScheduleLineResponse])
async def get_loan_schedule(
    loan_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> list[RepaymentScheduleLine]:
    require_permission(staff.role, "loans:read")
    if await tenant_db.get(Loan, loan_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    schedule = (
        await tenant_db.execute(
            select(RepaymentSchedule).where(
                RepaymentSchedule.loan_id == loan_id, RepaymentSchedule.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if schedule is None:
        return []
    result = await tenant_db.execute(
        select(RepaymentScheduleLine)
        .where(RepaymentScheduleLine.schedule_id == schedule.id)
        .order_by(RepaymentScheduleLine.installment_number)
    )
    return list(result.scalars().all())
