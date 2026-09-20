"""Background scheduler — the "real tâche de fond" the Phase 5 exit criterion asks
for, distinct from app/worker.py (which executes jobs; this only decides when to
enqueue backup/verification jobs in the first place).

Run as its own process, alongside the API and the worker:

    python -m app.scheduler
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.core.timeutil import as_aware_utc, utcnow
from app.db.session import AsyncSessionLocal
from app.models.backup import Backup, BackupStatus, BackupType
from app.models.cluster import Cluster, ClusterStatus, ClusterTopology
from app.models.cluster_event import ClusterEvent
from app.models.cluster_member import ClusterMember, ClusterMemberRole
from app.models.database import Database, DatabaseStatus
from app.models.node import Node
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.usage_record import UsageMetric, UsageRecord
from app.services.agent_client import AgentRequestError, AgentUnreachableError, call_agent
from app.services.backup_orchestrator import backup_storage_key
from app.services.billing import compute_invoice_for_subscription
from app.services.ha_orchestrator import NoHealthyReplicaError, execute_failover
from app.services.jobs import enqueue
from app.services.node_health import is_eligible_for_placement
from app.services.notification_service import notify_invoice_created
from app.services.orchestrator import get_primary_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")

TICK_INTERVAL_SECONDS = 60
# Re-check a completed backup's restorability periodically, not just once — a
# backup that verified fine a month ago says less than one verified last week.
REVERIFY_INTERVAL_DAYS = 7


async def enqueue_due_backups() -> int:
    enqueued = 0
    async with AsyncSessionLocal() as db:
        databases = (
            (await db.execute(select(Database).where(Database.status == DatabaseStatus.RUNNING)))
            .scalars()
            .all()
        )
        for database in databases:
            policy = database.backup_policy or {}
            if not policy.get("enabled"):
                continue
            frequency_hours = policy.get("frequency_hours", 24)

            last_backup = (
                await db.execute(
                    select(Backup)
                    .where(Backup.database_id == database.id, Backup.type == BackupType.AUTOMATIC)
                    .order_by(Backup.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if last_backup is not None:
                age_hours = (utcnow() - as_aware_utc(last_backup.created_at)).total_seconds() / 3600
                if age_hours < frequency_hours:
                    continue

            backup_id = uuid.uuid4()
            backup = Backup(
                id=backup_id,
                database_id=database.id,
                type=BackupType.AUTOMATIC,
                storage_key=backup_storage_key(database.id, backup_id),
            )
            db.add(backup)
            await db.flush()
            await enqueue(
                db,
                type="backup_database",
                payload={"backup_id": str(backup.id)},
                resource_type="backup",
                resource_id=backup.id,
            )
            enqueued += 1
            logger.info("scheduled automatic backup %s for database %s", backup.id, database.id)
        await db.commit()
    return enqueued


async def enqueue_due_verifications() -> int:
    enqueued = 0
    cutoff = utcnow() - dt.timedelta(days=REVERIFY_INTERVAL_DAYS)
    async with AsyncSessionLocal() as db:
        candidates = (
            (
                await db.execute(
                    select(Backup).where(
                        Backup.status.in_([BackupStatus.COMPLETED, BackupStatus.VERIFIED])
                    )
                )
            )
            .scalars()
            .all()
        )
        for backup in candidates:
            if backup.verified_at is not None and as_aware_utc(backup.verified_at) > cutoff:
                continue
            await enqueue(
                db,
                type="verify_backup",
                payload={"backup_id": str(backup.id)},
                resource_type="backup",
                resource_id=backup.id,
            )
            enqueued += 1
            logger.info("scheduled verification for backup %s", backup.id)
        await db.commit()
    return enqueued


async def purge_expired_automatic_backups() -> int:
    """Never touches manual backups — an operator who took one clearly wanted it
    kept, and auto-expiring it would be a surprising, hard-to-reverse action."""
    purged = 0
    async with AsyncSessionLocal() as db:
        databases = (await db.execute(select(Database))).scalars().all()
        for database in databases:
            retention_days = (database.backup_policy or {}).get("retention_days")
            if not retention_days:
                continue
            cutoff = utcnow() - dt.timedelta(days=retention_days)
            expired = (
                (
                    await db.execute(
                        select(Backup).where(
                            Backup.database_id == database.id,
                            Backup.type == BackupType.AUTOMATIC,
                            Backup.status != BackupStatus.PURGED,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for backup in expired:
                if as_aware_utc(backup.created_at) > cutoff:
                    continue
                if database.cluster_id is not None:
                    try:
                        node = await get_primary_node(db, database.cluster_id)
                        await call_agent(
                            node,
                            "DELETE",
                            "/v1/backups",
                            params={"storage_key": backup.storage_key},
                        )
                    except AgentUnreachableError:
                        # Best-effort: the metadata purge below still records intent
                        # to expire this backup even if the physical delete didn't
                        # happen yet — it'll be retried next tick since the row
                        # stays visible to this same query until PURGED is set.
                        logger.warning(
                            "could not delete backup object %s from storage; will retry",
                            backup.storage_key,
                        )
                        continue
                backup.status = BackupStatus.PURGED
                purged += 1
                logger.info("purged expired automatic backup %s", backup.id)
        await db.commit()
    return purged


async def check_and_failover_unhealthy_clusters() -> int:
    """The Health Monitor + Failover Controller of docs/architecture/05 §5.3: for
    every HA cluster, if its primary is unreachable/stale (same effective_status
    rule the Orchestrator uses for placement — cf. app/services/node_health.py),
    promote the best replica automatically."""
    failovers = 0
    async with AsyncSessionLocal() as db:
        clusters = (
            (
                await db.execute(
                    select(Cluster).where(
                        Cluster.topology == ClusterTopology.PRIMARY_REPLICA,
                        Cluster.status == ClusterStatus.ACTIVE,
                    )
                )
            )
            .scalars()
            .all()
        )
        for cluster in clusters:
            primary_member = (
                await db.execute(
                    select(ClusterMember).where(
                        ClusterMember.cluster_id == cluster.id,
                        ClusterMember.role == ClusterMemberRole.PRIMARY,
                    )
                )
            ).scalar_one_or_none()
            if primary_member is None:
                continue  # already mid-failover or misconfigured — nothing to compare against

            primary_node = await db.get(Node, primary_member.node_id)
            if primary_node is not None and is_eligible_for_placement(primary_node):
                continue  # primary looks healthy

            logger.warning(
                "primary node %s of cluster %s looks unhealthy — starting automatic failover",
                primary_member.node_id,
                cluster.id,
            )
            try:
                result = await execute_failover(db, cluster.id, automatic=True)
                await db.commit()
                failovers += 1
                logger.warning(
                    "automatic failover completed for cluster %s: promoted node %s",
                    cluster.id,
                    result["promoted_node_id"],
                )
            except NoHealthyReplicaError as exc:
                db.add(
                    ClusterEvent(
                        cluster_id=cluster.id,
                        event_type="FAILOVER_FAILED",
                        data={"reason": str(exc)},
                    )
                )
                await db.commit()
                logger.error("automatic failover for cluster %s failed: %s", cluster.id, exc)
    return failovers


async def meter_usage() -> int:
    """Phase 10 — cf. docs/architecture/08 §8.12: UsageRecord is written here,
    once per tick, from a real agent call — never fabricated or derived after
    the fact in an API endpoint. Each RUNNING database gets one storage_gb_hours
    reading (real, from the agent's pg_database_size-based /metrics call) and
    one connections reading (real, a live pg_stat_activity count) per tick.

    cpu_hours is the one exception worth calling out: there is no per-database
    CPU cgroup on a shared cluster (cf. Phase 7 — resize only enforces a
    connection limit, not real CPU isolation), so there is nothing to actually
    *measure*. It is billed on ALLOCATED capacity (cpu_limit) while RUNNING
    instead — an honest, documented choice (allocated-capacity billing, the
    same model most shared-vCPU cloud providers use), not a number invented to
    fill the column.

    egress_gb is never emitted: no component anywhere in this platform counts
    network bytes today. Deliberately left unbilled rather than guessed at.
    """
    metered = 0
    hours_elapsed = Decimal(TICK_INTERVAL_SECONDS) / Decimal(3600)
    async with AsyncSessionLocal() as db:
        now = utcnow()
        period_start = now - dt.timedelta(seconds=TICK_INTERVAL_SECONDS)
        databases = (
            (await db.execute(select(Database).where(Database.status == DatabaseStatus.RUNNING)))
            .scalars()
            .all()
        )
        for database in databases:
            try:
                node = await get_primary_node(db, database.cluster_id)
                resp = await call_agent(
                    node, "GET", f"/v1/database/{database.physical_name}/metrics"
                )
                metrics = resp.json()
            except (AgentUnreachableError, AgentRequestError):
                # Transient — the next tick tries again. Never fabricate a
                # reading for a database we couldn't actually reach.
                continue

            storage_gb = Decimal(metrics["size_bytes"]) / Decimal(1024**3)
            db.add(
                UsageRecord(
                    database_id=database.id,
                    metric=UsageMetric.STORAGE_GB_HOURS,
                    value=storage_gb * hours_elapsed,
                    period_start=period_start,
                    period_end=now,
                )
            )
            db.add(
                UsageRecord(
                    database_id=database.id,
                    metric=UsageMetric.CPU_HOURS,
                    value=Decimal(database.cpu_limit) * hours_elapsed,
                    period_start=period_start,
                    period_end=now,
                )
            )
            db.add(
                UsageRecord(
                    database_id=database.id,
                    metric=UsageMetric.CONNECTIONS,
                    value=Decimal(metrics["active_connections"]),
                    period_start=period_start,
                    period_end=now,
                )
            )
            metered += 1
        await db.commit()
    return metered


async def generate_due_invoices() -> int:
    """cf. app/services/billing.py — one Invoice per subscription whose current
    billing period has ended, computed purely from UsageRecord, never a
    manually-entered amount."""
    generated = 0
    async with AsyncSessionLocal() as db:
        due = (
            (
                await db.execute(
                    select(Subscription).where(
                        Subscription.current_period_end <= utcnow(),
                        Subscription.status == SubscriptionStatus.ACTIVE,
                    )
                )
            )
            .scalars()
            .all()
        )
        for subscription in due:
            invoice = await compute_invoice_for_subscription(db, subscription)
            await notify_invoice_created(
                db,
                subscription.organization_id,
                invoice.id,
                invoice.total_amount,
                invoice.currency,
                invoice.period_end.date().isoformat(),
            )
            generated += 1
        await db.commit()
    return generated


async def tick() -> None:
    await enqueue_due_backups()
    await enqueue_due_verifications()
    await purge_expired_automatic_backups()
    await check_and_failover_unhealthy_clusters()
    await meter_usage()
    await generate_due_invoices()


async def main() -> None:
    logger.info("backup scheduler started (tick every %ss)", TICK_INTERVAL_SECONDS)
    while True:
        try:
            await tick()
        except Exception:  # noqa: BLE001 — must never crash the scheduler loop
            logger.exception("scheduler tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
