"""Central audit logging (cf. docs/architecture/04-securite-et-isolation.md §4.7).

Every sensitive mutation goes through `record_audit` so no code path can silently
skip the audit trail. Never pass raw secrets in `before`/`after`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

_REDACTED_KEYS = {"password", "password_hash", "secret", "token", "api_key", "key_hash"}


def _redact(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    return {k: ("***" if k.lower() in _REDACTED_KEYS else v) for k, v in payload.items()}


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
    result: str = "success",
) -> None:
    entry = AuditLog(
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before=_redact(before),
        after=_redact(after),
        ip_address=ip_address,
        result=result,
    )
    db.add(entry)
    await db.flush()
