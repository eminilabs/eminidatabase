import datetime as dt
import uuid

from pydantic import BaseModel

from mf_app.models.job import MFJobStatus


class MFJobResponse(BaseModel):
    id: uuid.UUID
    type: str
    status: MFJobStatus
    error: str | None
    result: dict | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
