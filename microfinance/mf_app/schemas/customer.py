import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from mf_app.models.tenant.customer import KYCStatus


class CustomerCreate(BaseModel):
    branch_id: uuid.UUID
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    identity_documents: dict = Field(default_factory=dict)


class CustomerResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    full_name: str
    phone: str | None
    kyc_status: KYCStatus
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class CustomerKYCUpdate(BaseModel):
    kyc_status: KYCStatus = Field(
        description="Must be 'verified' or 'rejected' — 'pending' is the initial "
        "default only, never a transition target."
    )


class SavingsAccountOpen(BaseModel):
    product_id: uuid.UUID
    opening_deposit: Decimal = Field(default=Decimal("0"), ge=0)
    # Required only when opening_deposit > 0 (validated in the endpoint, which
    # needs the product's min_opening_balance from the DB to fully validate
    # anyway — cf. app/api/v1/endpoints/savings.py).
    idempotency_key: str | None = Field(default=None, max_length=255)


class SavingsTransactionRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
