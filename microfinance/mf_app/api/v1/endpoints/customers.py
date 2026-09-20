from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import get_current_staff_user, get_tenant_db
from mf_app.models.staff_user import MFStaffUser
from mf_app.models.tenant.branch import Branch
from mf_app.models.tenant.customer import Customer
from mf_app.schemas.customer import CustomerCreate, CustomerKYCUpdate, CustomerResponse
from mf_app.services.rbac import require_permission

router = APIRouter(prefix="/institutions/{institution_slug}/customers", tags=["customers"])


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Customer:
    require_permission(staff.role, "customers:manage")
    if await tenant_db.get(Branch, payload.branch_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Branch not found")

    customer = Customer(
        branch_id=payload.branch_id,
        full_name=payload.full_name,
        phone=payload.phone,
        identity_documents=payload.identity_documents,
    )
    tenant_db.add(customer)
    await tenant_db.commit()
    await tenant_db.refresh(customer)
    return customer


@router.get("", response_model=list[CustomerResponse])
async def list_customers(
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> list[Customer]:
    require_permission(staff.role, "customers:read")
    result = await tenant_db.execute(select(Customer))
    return list(result.scalars().all())


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Customer:
    require_permission(staff.role, "customers:read")
    customer = await tenant_db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.patch("/{customer_id}/kyc", response_model=CustomerResponse)
async def update_kyc_status(
    customer_id: uuid.UUID,
    payload: CustomerKYCUpdate,
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> Customer:
    require_permission(staff.role, "customers:manage")
    customer = await tenant_db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Customer not found")
    customer.kyc_status = payload.kyc_status
    await tenant_db.commit()
    await tenant_db.refresh(customer)
    return customer
