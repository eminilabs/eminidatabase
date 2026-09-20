import uuid

from pydantic import BaseModel, Field


class RegionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9-]{1,49}$")
    name: str = Field(min_length=2, max_length=200)


class RegionResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    active: bool

    model_config = {"from_attributes": True}
