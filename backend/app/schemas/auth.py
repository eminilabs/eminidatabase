import uuid

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    otp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    mfa_enabled: bool

    model_config = {"from_attributes": True}


class MfaEnableResponse(BaseModel):
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    otp_code: str
