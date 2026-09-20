import uuid
from decimal import Decimal

from pydantic import BaseModel


class TrialBalanceLine(BaseModel):
    account_type: str
    account_id: uuid.UUID | None
    label: str
    normal_side: str
    balance: Decimal


class TrialBalanceResponse(BaseModel):
    lines: list[TrialBalanceLine]
    total_debit_side: Decimal
    total_credit_side: Decimal
    balanced: bool


class LoanPortfolioResponse(BaseModel):
    active_loan_count: int
    total_principal_disbursed: Decimal
    total_outstanding_principal: Decimal
