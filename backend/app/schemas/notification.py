import datetime as dt
import uuid

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    data: dict
    read_at: dt.datetime | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
