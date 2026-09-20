import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr, Field

from mf_app.models.institution import MFInstitutionStatus


class InstitutionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9-]{1,62}$")
    region_code: str = Field(min_length=2, max_length=50)
    currency: str = Field(default="XOF", min_length=3, max_length=3)
    admin_email: EmailStr


class InstitutionResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: MFInstitutionStatus
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class InstitutionCreated(BaseModel):
    institution: InstitutionResponse
    job_id: uuid.UUID
    # Shown once, exactly like an API key or a webhook secret elsewhere in this
    # codebase — never re-readable after this response (cf. app/services/
    # onboarding.py's docstring for why this is synchronous, not part of the job).
    admin_email: str
    admin_password: str
