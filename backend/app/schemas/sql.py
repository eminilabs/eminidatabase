import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field


class SqlExecuteRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    # Which of the database's roles to run as — defaults to the original owner
    # (APP scope) credential. Running as a readonly role is how a user gets the
    # editor to *actually* enforce read-only, rather than trusting the client.
    role_id: uuid.UUID | None = None


class SqlExecuteResponse(BaseModel):
    status: str  # succeeded|failed
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    error: str | None


class SavedQueryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=10000)


class SavedQueryResponse(BaseModel):
    id: uuid.UUID
    name: str
    query_text: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class QueryExecutionResponse(BaseModel):
    id: uuid.UUID
    query_text: str
    status: str
    row_count: int | None
    duration_ms: int | None
    error: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
