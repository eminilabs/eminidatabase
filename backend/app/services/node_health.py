"""Computes a Node's effective status from heartbeat staleness.

Kept separate from the ORM model (cf. docs/architecture/03 §"Enregistrement d'un
node") so the Database Orchestrator (Phase 3) reuses the exact same rule when
deciding placement eligibility — a node isn't excluded from placement one way in
the dashboard and a different way in the scheduler.
"""

from __future__ import annotations

from app.core.timeutil import as_aware_utc, utcnow
from app.models.node import Node, NodeStatus

HEARTBEAT_STALE_SECONDS = 60


def effective_status(node: Node) -> str:
    if node.status != NodeStatus.ACTIVE:
        return node.status.value
    if node.last_heartbeat_at is None:
        return "offline"
    age = (utcnow() - as_aware_utc(node.last_heartbeat_at)).total_seconds()
    return "offline" if age > HEARTBEAT_STALE_SECONDS else "active"


def is_eligible_for_placement(node: Node) -> bool:
    return effective_status(node) == "active"
