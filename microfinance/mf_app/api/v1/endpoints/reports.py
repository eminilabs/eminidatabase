from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.dependencies import get_current_staff_user, get_tenant_db
from mf_app.models.staff_user import MFStaffUser
from mf_app.schemas.reports import LoanPortfolioResponse, TrialBalanceResponse
from mf_app.services.rbac import require_permission
from mf_app.services.reports import get_loan_portfolio, get_trial_balance

router = APIRouter(prefix="/institutions/{institution_slug}/reports", tags=["reports"])


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def trial_balance(
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    require_permission(staff.role, "reports:read")
    return await get_trial_balance(tenant_db)


@router.get("/loan-portfolio", response_model=LoanPortfolioResponse)
async def loan_portfolio(
    staff: MFStaffUser = Depends(get_current_staff_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    require_permission(staff.role, "reports:read")
    return await get_loan_portfolio(tenant_db)
