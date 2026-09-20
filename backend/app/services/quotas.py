"""Quota enforcement — the "Quota du plan OK?" gate from docs/architecture/
03-database-orchestrator-et-agent.md's provisioning flow diagram. Checked once,
here, before a database is ever created — never re-derived ad hoc in the
endpoint or skipped because "it's just one more database"."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Database, DatabaseStatus
from app.models.plan import Plan
from app.models.project import Project
from app.models.subscription import Subscription

_TERMINAL_STATUSES = {DatabaseStatus.DELETING, DatabaseStatus.DELETED}

# One asyncio.Lock per organization, serializing "check quota, then create" so
# two concurrent database-creation requests for the same org can never both
# pass the quota check before either commits — a real race a concurrency test
# caught: without this, two simultaneous requests on a free plan (max 1
# database) both got 202. A single dict works because this Control Plane is a
# single process by design today (cf. the jobs-table queue, the in-memory rate
# limiter, the single scheduler/worker) — a multi-instance deployment would
# need a real distributed lock (e.g. a Postgres advisory lock keyed by
# organization_id) instead, noted as a future increment, not pretended away.
_organization_locks: dict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)


def get_organization_lock(organization_id: uuid.UUID) -> asyncio.Lock:
    return _organization_locks[organization_id]


class QuotaExceededError(Exception):
    pass


async def get_active_plan(db: AsyncSession, organization_id: uuid.UUID) -> Plan:
    subscription = (
        await db.execute(
            select(Subscription).where(Subscription.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise RuntimeError(f"Organization {organization_id} has no subscription")
    plan = await db.get(Plan, subscription.plan_id)
    if plan is None:
        raise RuntimeError(f"Subscription {subscription.id} references a missing plan")
    return plan


async def check_database_quota(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    additional_storage_gb: int,
    additional_cpu: int,
) -> None:
    plan = await get_active_plan(db, organization_id)
    quotas = plan.quotas

    databases = (
        (
            await db.execute(
                select(Database)
                .join(Project, Project.id == Database.project_id)
                .where(
                    Project.organization_id == organization_id,
                    Database.status.notin_(_TERMINAL_STATUSES),
                )
            )
        )
        .scalars()
        .all()
    )

    max_databases = quotas.get("max_databases")
    if max_databases is not None and len(databases) + 1 > max_databases:
        raise QuotaExceededError(f"Plan '{plan.name}' allows at most {max_databases} databases")

    max_storage_gb = quotas.get("max_storage_gb")
    if max_storage_gb is not None:
        current_storage = sum(d.storage_limit_gb for d in databases)
        if current_storage + additional_storage_gb > max_storage_gb:
            raise QuotaExceededError(
                f"Plan '{plan.name}' allows at most {max_storage_gb} GB of storage total"
            )

    max_cpu_total = quotas.get("max_cpu_total")
    if max_cpu_total is not None:
        current_cpu = sum(d.cpu_limit for d in databases)
        if current_cpu + additional_cpu > max_cpu_total:
            raise QuotaExceededError(
                f"Plan '{plan.name}' allows at most {max_cpu_total} total vCPUs"
            )
