import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr, Field

from mf_app.models.staff_user import MFStaffRole


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    role: MFStaffRole
    # Required for branch_manager/loan_officer/teller, must be omitted for
    # institution_admin (validated in the endpoint, not here, since it needs a
    # DB lookup for the branch — cf. app/api/v1/endpoints/staff.py).
    branch_id: uuid.UUID | None = None


class StaffResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: MFStaffRole
    is_active: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}
