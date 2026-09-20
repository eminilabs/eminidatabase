import uuid

from pydantic import BaseModel, EmailStr

from mf_app.models.staff_user import MFStaffRole


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str


class StaffLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StaffMeResponse(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    email: str
    role: MFStaffRole

    model_config = {"from_attributes": True}
