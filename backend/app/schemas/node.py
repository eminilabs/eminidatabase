import datetime as dt
import uuid

from pydantic import BaseModel, Field


class NodeRegisterRequest(BaseModel):
    hostname: str = Field(min_length=2, max_length=255)
    region_code: str = Field(min_length=2, max_length=50)
    csr_pem: str
    ip_address: str | None = None
    cpu_total: int = Field(gt=0)
    ram_total_mb: int = Field(gt=0)
    storage_total_gb: int = Field(gt=0)
    agent_version: str | None = None
    agent_port: int = 9443
    postgres_port: int = 5432


class NodeRegisterResponse(BaseModel):
    node_id: uuid.UUID
    node_secret: str
    certificate_pem: str
    ca_certificate_pem: str
    heartbeat_interval_seconds: int = 20


class NodeHeartbeatRequest(BaseModel):
    cpu_used: float | None = None
    ram_used_mb: int | None = None
    storage_used_gb: int | None = None
    agent_version: str | None = None


class NodeResponse(BaseModel):
    id: uuid.UUID
    region_id: uuid.UUID
    hostname: str
    ip_address: str | None
    cpu_total: int
    ram_total_mb: int
    storage_total_gb: int
    cpu_used: float | None
    ram_used_mb: int | None
    storage_used_gb: int | None
    agent_version: str | None
    agent_port: int
    postgres_port: int
    status: str
    effective_status: str
    last_heartbeat_at: dt.datetime | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class NodeHealthCheckResult(BaseModel):
    node_id: uuid.UUID
    reachable: bool
    detail: str
    checked_at: dt.datetime
