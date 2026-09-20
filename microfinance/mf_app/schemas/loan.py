import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from mf_app.models.tenant.loan import LoanStatus
from mf_app.models.tenant.loan_product import AmortizationMethod
from mf_app.models.tenant.repayment_schedule import RepaymentLineStatus


class LoanProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=30)
    amortization_method: AmortizationMethod
    periodic_interest_rate: Decimal = Field(ge=0, le=1)
    min_principal: Decimal = Field(gt=0)
    max_principal: Decimal = Field(gt=0)
    min_term_months: int = Field(ge=1)
    max_term_months: int = Field(ge=1)


class LoanProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    amortization_method: AmortizationMethod
    periodic_interest_rate: Decimal
    min_principal: Decimal
    max_principal: Decimal
    min_term_months: int
    max_term_months: int
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class LoanCreate(BaseModel):
    customer_id: uuid.UUID
    product_id: uuid.UUID
    principal: Decimal = Field(gt=0)
    term_months: int = Field(ge=1)


class LoanResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    product_id: uuid.UUID
    principal: Decimal
    term_months: int
    status: LoanStatus
    outstanding_principal: Decimal
    approved_at: dt.datetime | None
    disbursed_at: dt.datetime | None
    closed_at: dt.datetime | None
    rejection_reason: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class LoanRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class LoanDisburseRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)


class LoanRepayRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=255)


class RepaymentScheduleLineResponse(BaseModel):
    installment_number: int
    due_date: dt.date
    principal_due: Decimal
    interest_due: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    status: RepaymentLineStatus

    model_config = {"from_attributes": True}
