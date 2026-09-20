"""SQL Editor query execution (cahier des charges §35).

Connects directly to the customer's database *as the Postgres role the caller
picked* — Postgres's own privilege system is what enforces "le SQL Editor doit
appliquer strictement les permissions de l'utilisateur", not an app-level
reimplementation of it that could drift out of sync with the real grants.

Deliberately out of scope for this phase (documented, not forgotten): TLS to the
customer's Postgres (Phase 11 hardening), multi-statement queries, streaming very
large result sets — capped at MAX_RETURNED_ROWS instead.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import time
import uuid as uuid_mod

import asyncpg

from app.models.database import Database
from app.models.database_credential import DatabaseCredential
from app.services.secrets import decrypt_secret

MAX_RETURNED_ROWS = 500
STATEMENT_TIMEOUT_MS = 15_000


@dataclasses.dataclass
class SqlExecutionResult:
    status: str  # succeeded|failed
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    duration_ms: int
    error: str | None


def _jsonable(value):
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid_mod.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray):
        return value.hex()
    return value


async def execute_query(
    database: Database, credential: DatabaseCredential, query: str
) -> SqlExecutionResult:
    password = decrypt_secret(credential.encrypted_password)
    start = time.monotonic()

    try:
        conn = await asyncpg.connect(
            host=database.connection_host,
            port=database.connection_port,
            user=credential.role_name,
            password=password,
            database=database.physical_name,
            timeout=10,
        )
    except (OSError, asyncpg.PostgresError) as exc:
        return SqlExecutionResult(
            status="failed",
            columns=[],
            rows=[],
            row_count=0,
            truncated=False,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=f"Could not connect as {credential.role_name}: {exc}",
        )

    try:
        await conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        try:
            records = await conn.fetch(query)
        except asyncpg.PostgresError as exc:
            return SqlExecutionResult(
                status="failed",
                columns=[],
                rows=[],
                row_count=0,
                truncated=False,
                duration_ms=int((time.monotonic() - start) * 1000),
                error=str(exc),
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        columns = list(records[0].keys()) if records else []
        total = len(records)
        truncated = total > MAX_RETURNED_ROWS
        rows = [[_jsonable(v) for v in r.values()] for r in records[:MAX_RETURNED_ROWS]]

        return SqlExecutionResult(
            status="succeeded",
            columns=columns,
            rows=rows,
            row_count=total,
            truncated=truncated,
            duration_ms=duration_ms,
            error=None,
        )
    finally:
        await conn.close()
