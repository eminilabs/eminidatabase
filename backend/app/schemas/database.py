import datetime as dt
import uuid

from pydantic import BaseModel, Field

from app.models.database import IsolationLevel


class DatabaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9-]{1,62}$")
    region_code: str = Field(min_length=2, max_length=50)
    isolation_level: IsolationLevel = IsolationLevel.SHARED
    cpu_limit: int = Field(default=1, ge=1, le=32)
    ram_limit_mb: int = Field(default=1024, ge=256, le=262144)
    storage_limit_gb: int = Field(default=10, ge=1, le=4096)


class DatabaseResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    region_id: uuid.UUID
    cluster_id: uuid.UUID | None
    name: str
    isolation_level: IsolationLevel
    status: str
    cpu_limit: int
    ram_limit_mb: int
    storage_limit_gb: int
    connection_host: str | None
    connection_port: int | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class DatabaseCreateAccepted(BaseModel):
    database: DatabaseResponse
    job_id: uuid.UUID


class DatabaseResize(BaseModel):
    cpu_limit: int = Field(ge=1, le=32)
    ram_limit_mb: int = Field(ge=256, le=262144)
    storage_limit_gb: int = Field(ge=1, le=4096)


class MigrateRequest(BaseModel):
    target_node_id: uuid.UUID


class DatabaseConnectionResponse(BaseModel):
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl_mode: str = "require"
    connection_string: str
