import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator

from app.models.webhook import SUPPORTED_EVENT_TYPES


class WebhookCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    event_types: list[str] = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def _require_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Webhook URLs must use https://")
        return value

    @field_validator("event_types")
    @classmethod
    def _validate_event_types(cls, value: list[str]) -> list[str]:
        unknown = set(value) - SUPPORTED_EVENT_TYPES
        if unknown:
            raise ValueError(
                f"Unknown event type(s): {sorted(unknown)}. "
                f"Supported: {sorted(SUPPORTED_EVENT_TYPES)}"
            )
        return value


class WebhookCreated(BaseModel):
    id: uuid.UUID
    url: str
    event_types: list[str]
    secret: str  # shown once


class WebhookResponse(BaseModel):
    id: uuid.UUID
    url: str
    event_types: list[str]
    is_active: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    status: str
    response_code: int | None
    error: str | None
    created_at: dt.datetime
    delivered_at: dt.datetime | None

    model_config = {"from_attributes": True}
