import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from mf_app.models.tenant.savings_account import SavingsAccountStatus


class SavingsProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=30)
    annual_interest_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    min_opening_balance: Decimal = Field(default=Decimal("0"), ge=0)


class SavingsProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    annual_interest_rate: Decimal
    min_opening_balance: Decimal
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class SavingsAccountResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    product_id: uuid.UUID
    account_number: str
    status: SavingsAccountStatus
    balance_cached: Decimal
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    id: uuid.UUID
    type: str
    amount: Decimal
    description: str | None
    idempotency_key: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}
