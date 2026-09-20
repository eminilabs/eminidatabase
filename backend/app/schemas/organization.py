import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.membership import MembershipRole


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=200, pattern=r"^[a-z][a-z0-9-]{1,199}$")


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: dt.datetime
    role: MembershipRole | None = None

    model_config = {"from_attributes": True}


class MembershipCreate(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.DEVELOPER


class MembershipResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: MembershipRole
    created_at: dt.datetime

    model_config = {"from_attributes": True}
