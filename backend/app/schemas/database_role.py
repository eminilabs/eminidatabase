import datetime as dt
import uuid

from pydantic import BaseModel, Field

from app.models.database_credential import CredentialScope


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    # ADMIN is reserved for the provisioning-time owner role — never creatable here.
    scope: CredentialScope = Field(default=CredentialScope.APP)


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str | None
    role_name: str
    scope: CredentialScope
    is_primary: bool
    created_at: dt.datetime
    rotated_at: dt.datetime | None

    model_config = {"from_attributes": True}


class RoleCreated(BaseModel):
    id: uuid.UUID
    name: str
    role_name: str
    password: str  # shown once


class RoleRotated(BaseModel):
    role_name: str
    password: str
