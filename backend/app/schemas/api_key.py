import datetime as dt
import uuid

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    scopes: dict = Field(default_factory=dict)


class ApiKeyCreated(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    api_key: str  # returned once, never persisted or retrievable again


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None

    model_config = {"from_attributes": True}
