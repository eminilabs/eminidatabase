"""RBAC permission matrix (cf. docs/architecture/04-securite-et-isolation.md §4.2).

One explicit table, checked from a single place — never scattered ad hoc role
checks across endpoint code.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.models.membership import MembershipRole as R

_PERMISSIONS: dict[str, set[R]] = {
    "org:delete": {R.OWNER},
    "org:update_settings": {R.OWNER, R.ADMIN},
    "org:manage_members": {R.OWNER, R.ADMIN},
    "org:read": {R.OWNER, R.ADMIN, R.DEVELOPER, R.BILLING, R.READONLY},
    "project:create": {R.OWNER, R.ADMIN, R.DEVELOPER},
    "project:delete": {R.OWNER, R.ADMIN},
    "project:read": {R.OWNER, R.ADMIN, R.DEVELOPER, R.BILLING, R.READONLY},
    "api_key:manage": {R.OWNER, R.ADMIN},
    "billing:read": {R.OWNER, R.ADMIN, R.BILLING},
    "database:create": {R.OWNER, R.ADMIN, R.DEVELOPER},
    "database:read": {R.OWNER, R.ADMIN, R.DEVELOPER, R.BILLING, R.READONLY},
    "database:delete": {R.OWNER, R.ADMIN},
    "database:manage": {R.OWNER, R.ADMIN, R.DEVELOPER},
    # Deliberately narrower than database:read — this hands back a live plaintext
    # password (cf. GET .../connection), so BILLING/READONLY (dashboard visibility
    # roles) must not get it just because they can see a database exists.
    "database:connect": {R.OWNER, R.ADMIN, R.DEVELOPER},
    "database:roles:manage": {R.OWNER, R.ADMIN, R.DEVELOPER},
    "database:extensions:manage": {R.OWNER, R.ADMIN, R.DEVELOPER},
    "database:sql:execute": {R.OWNER, R.ADMIN, R.DEVELOPER},
    "database:observe": {R.OWNER, R.ADMIN, R.DEVELOPER, R.BILLING, R.READONLY},
    "database:backups:manage": {R.OWNER, R.ADMIN, R.DEVELOPER},
    # Same tier as api_key:manage: a webhook both receives event payloads and
    # points at an arbitrary external URL — an infra-adjacent trust decision, not
    # routine project work.
    "webhooks:manage": {R.OWNER, R.ADMIN},
    # Changing a plan or confirming a payment is strictly narrower than
    # billing:read (doc 04 §4.2: admin can read usage/invoices but does not
    # manage billing — only the owner does).
    "subscription:manage": {R.OWNER},
}


def has_permission(role: R, action: str) -> bool:
    allowed = _PERMISSIONS.get(action)
    if allowed is None:
        raise ValueError(f"Unknown RBAC action: {action}")
    return role in allowed


def require_permission(role: R, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role.value}' is not allowed to perform '{action}'",
        )
