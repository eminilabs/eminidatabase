import datetime as dt
import uuid

from pydantic import BaseModel, Field


class BranchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=20)


class BranchResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}
