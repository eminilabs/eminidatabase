import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.invoice import InvoiceStatus
from app.models.payment import PaymentProviderName, PaymentStatus
from app.models.subscription import SubscriptionStatus


class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    quotas: dict = Field(default_factory=dict)
    pricing: dict = Field(default_factory=dict)


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    quotas: dict
    pricing: dict
    is_active: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    current_period_start: dt.datetime
    current_period_end: dt.datetime

    model_config = {"from_attributes": True}


class SubscriptionUpdate(BaseModel):
    plan_id: uuid.UUID


class UsageSummaryLine(BaseModel):
    metric: str
    total: Decimal


class UsageSummaryResponse(BaseModel):
    period_start: dt.datetime
    period_end: dt.datetime
    lines: list[UsageSummaryLine]


class InvoiceLineItemResponse(BaseModel):
    description: str
    metric: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    period_start: dt.datetime
    period_end: dt.datetime
    status: InvoiceStatus
    total_amount: Decimal
    currency: str
    finalized_at: dt.datetime | None
    paid_at: dt.datetime | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class InvoiceDetailResponse(InvoiceResponse):
    line_items: list[InvoiceLineItemResponse]


class CryptoPaymentRequest(BaseModel):
    # e.g. "usdtbsc", "btc", "eth" — cf. NOWPayments' /full-currencies for the
    # full list this sandbox/account is enabled for.
    pay_currency: str | None = None


class MobileMoneyPaymentRequest(BaseModel):
    # cf. app/services/payment_providers/fedapay.py's MOBILE_MONEY_OPERATORS for
    # supported values (e.g. "mtn_ci", "moov").
    mode: str
    phone_number: str = Field(min_length=6, max_length=20)


class PaymentResponse(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    provider: PaymentProviderName
    provider_payment_id: str | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    provider_status: str | None
    pay_address: str | None
    pay_amount: Decimal | None
    pay_currency: str | None
    payment_expires_at: dt.datetime | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
