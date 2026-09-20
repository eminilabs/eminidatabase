import datetime as dt

from pydantic import BaseModel, Field


class NodeRegistrationTokenCreate(BaseModel):
    region_code: str = Field(min_length=2, max_length=50)
    note: str | None = Field(default=None, max_length=255)
    expires_in_minutes: int = Field(default=60, gt=0, le=24 * 60)


class NodeRegistrationTokenCreated(BaseModel):
    token: str  # shown once, never retrievable again
    region_code: str
    expires_at: dt.datetime
