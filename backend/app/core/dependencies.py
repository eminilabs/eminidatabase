from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    decode_access_token,
    extract_api_key_prefix,
    verify_api_key,
    verify_node_secret,
)
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.membership import Membership
from app.models.node import Node
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


async def _authenticate_api_key(token: str, db: AsyncSession) -> User:
    """An API key authenticates AS the user who created it (their current
    membership/role, not a tier frozen at creation time) — same model as a
    GitHub personal access token, cf. app/models/api_key.py. Everything
    downstream (get_membership, require_permission, audit logging) then works
    unmodified, since this resolves to a real user with a real Membership row."""
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key"
    )
    prefix = extract_api_key_prefix(token)
    if prefix is None:
        raise invalid
    api_key = (
        await db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
    ).scalar_one_or_none()
    if (
        api_key is None
        or api_key.revoked_at is not None
        or api_key.user_id is None
        or not verify_api_key(token, api_key.key_hash)
    ):
        raise invalid
    user = await db.get(User, api_key.user_id)
    if user is None:
        raise invalid
    api_key.last_used_at = utcnow()
    await db.commit()
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    if extract_api_key_prefix(credentials.credentials) is not None:
        return await _authenticate_api_key(credentials.credentials, db)
    decoded = decode_access_token(credentials.credentials)
    if decoded is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await db.get(User, decoded.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.token_version != decoded.token_version:
        # Signed and not expired, but /auth/sessions/revoke-all moved on since
        # this one was issued — the security-relevant case, not a bug path.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked"
        )
    return user


async def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    """Gate for infrastructure-level endpoints (nodes, regions) — distinct from
    organization RBAC, since owning an organization grants no infra privileges."""
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin privileges required"
        )
    return current_user


async def get_membership(
    organization_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Membership:
    """Resolves the caller's membership in the org — the tenant boundary check.

    Every organization-scoped endpoint must depend on this (directly or via a
    permission check built on it) so a user can never act on an organization
    they do not belong to (cf. docs/architecture/04-securite-et-isolation.md §4.1).
    """
    result = await db.execute(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return membership


async def require_active_subscription(
    organization_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Blocks database-affecting actions (create, connect, run SQL, manage
    roles/extensions/backups) once an organization's subscription is
    PAST_DUE — an unpaid invoice still outstanding when the next billing
    period started (app/scheduler.py's generate_due_invoices). Read-only
    endpoints (database:read/observe, billing:read) are deliberately NOT
    gated by this, so a suspended org can still see its own data and go pay
    the outstanding invoice to restore access
    (payment_service._reactivate_if_current)."""
    subscription = (
        await db.execute(
            select(Subscription).where(Subscription.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if subscription is not None and subscription.status == SubscriptionStatus.PAST_DUE:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This organization has an unpaid invoice. Pay it to restore database access.",
        )


async def get_authenticated_node(
    node_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Node:
    """Authenticates a Data Plane Agent calling the Control Plane (registration
    already happened; this covers heartbeat and any future agent-initiated call)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer node secret"
        )
    node = await db.get(Node, node_id)
    if node is None or not verify_node_secret(credentials.credentials, node.node_secret_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid node credentials"
        )
    return node
