import datetime as dt
import uuid

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    attempts: int
    max_attempts: int
    error: str | None
    result: dict | None
    resource_type: str | None
    resource_id: uuid.UUID | None
    created_at: dt.datetime
    completed_at: dt.datetime | None

    model_config = {"from_attributes": True}
