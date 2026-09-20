import datetime as dt
import uuid

from pydantic import BaseModel, Field

from app.models.backup import BackupStatus, BackupType
from app.schemas.database import DatabaseResponse


class BackupResponse(BaseModel):
    id: uuid.UUID
    database_id: uuid.UUID
    type: BackupType
    status: BackupStatus
    size_bytes: int | None
    error: str | None
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    verified_at: dt.datetime | None
    verification_detail: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class BackupCreateAccepted(BaseModel):
    backup: BackupResponse
    job_id: uuid.UUID


class RestoreRequest(BaseModel):
    name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9-]{1,62}$")


class RestoreAccepted(BaseModel):
    database: DatabaseResponse
    job_id: uuid.UUID


class BackupPolicyUpdate(BaseModel):
    enabled: bool = True
    frequency_hours: int = Field(default=24, ge=1, le=24 * 30)
    retention_days: int = Field(default=7, ge=1, le=365)
