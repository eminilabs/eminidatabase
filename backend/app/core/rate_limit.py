"""API rate limiting (docs/architecture/04-securite-et-isolation.md §4.6 — "Rate
limiting sur l'API publique (par API key/IP), avec limites différenciées par
plan"). Documented since Phase 1, never implemented until this Phase 11
hardening pass — a confirmed gap, not a design decision to skip it.

In-memory sliding window, single-process only: correct for the single-VPS-per-
environment deployment target this platform is built for today (cf. the same
kind of documented simplification as the jobs-table queue in
app/services/jobs.py, or node health's staleness check) — a multi-instance
Control Plane deployment would need a shared store (Redis) instead, noted as a
future increment rather than pretended away.

Three tiers of key, in priority order:
1. Org-scoped routes (`/organizations/{org_id}/...`) — keyed by organization,
   limited according to that organization's active Plan (cf. Phase 10) so a
   paying plan genuinely gets a higher ceiling, not just nicer marketing copy.
2. Any other authenticated route — keyed by the caller's user id (decoded from
   the bearer JWT without a DB hit).
3. Unauthenticated routes (chiefly /auth/register and /auth/login) — keyed by
   client IP, with a deliberately tight limit: this is the platform's actual
   brute-force defense, the single most important case in §4.6.
"""

from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict, deque

from starlette.requests import Request

from app.core.security import decode_access_token

_WINDOW_SECONDS = 60
_UNAUTHENTICATED_LIMIT = 20
_DEFAULT_AUTHENTICATED_LIMIT = 300
_PLAN_LIMITS = {"free": 60, "pro": 600}
_PLAN_CACHE_TTL_SECONDS = 30

_ORG_PATH_RE = re.compile(r"^/api/v1/organizations/([0-9a-fA-F-]{36})(?:/|$)")

_buckets: dict[str, deque] = defaultdict(deque)
_plan_cache: dict[uuid.UUID, tuple[str, float]] = {}


def check_rate_limit(key: str, limit: int) -> tuple[bool, int]:
    now = time.monotonic()
    bucket = _buckets[key]
    while bucket and bucket[0] <= now - _WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = max(1, int(_WINDOW_SECONDS - (now - bucket[0])) + 1)
        return False, retry_after
    bucket.append(now)
    return True, 0


async def _plan_name_for_org(organization_id: uuid.UUID) -> str | None:
    cached = _plan_cache.get(organization_id)
    now = time.monotonic()
    if cached is not None and cached[1] > now:
        return cached[0]

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.plan import Plan
    from app.models.subscription import Subscription

    async with AsyncSessionLocal() as db:
        subscription = (
            await db.execute(
                select(Subscription).where(Subscription.organization_id == organization_id)
            )
        ).scalar_one_or_none()
        if subscription is None:
            return None
        plan = await db.get(Plan, subscription.plan_id)
        if plan is None:
            return None

    _plan_cache[organization_id] = (plan.name, now + _PLAN_CACHE_TTL_SECONDS)
    return plan.name


async def resolve_key_and_limit(request: Request) -> tuple[str, int]:
    org_match = _ORG_PATH_RE.match(request.url.path)
    if org_match:
        organization_id = uuid.UUID(org_match.group(1))
        plan_name = await _plan_name_for_org(organization_id)
        limit = _PLAN_LIMITS.get(plan_name, _DEFAULT_AUTHENTICATED_LIMIT) if plan_name else (
            _DEFAULT_AUTHENTICATED_LIMIT
        )
        return f"org:{organization_id}", limit

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        user_id = decode_access_token(auth_header[7:])
        if user_id is not None:
            return f"user:{user_id}", _DEFAULT_AUTHENTICATED_LIMIT

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}", _UNAUTHENTICATED_LIMIT
