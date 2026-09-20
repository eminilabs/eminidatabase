"""Streaming replication status and promotion.

cf. docs/architecture/05-backup-ha-scaling.md §5.3. Replica *provisioning* (the
initial pg_basebackup clone) is a day-0 infrastructure bootstrap step, not
something this always-on agent process does to itself — in production it runs
once, when a new node is brought up as a standby from the start (analogous to how
`bootstrap.py` handles this agent's own one-time registration). What the agent
provides on an ongoing basis is status reporting and promotion, both of which are
plain SQL/functions over the existing connection — no process control needed.
"""

from __future__ import annotations

import asyncio

import asyncpg


async def get_replication_status(conn: asyncpg.Connection) -> dict:
    in_recovery = await conn.fetchval("SELECT pg_is_in_recovery()")
    if not in_recovery:
        rows = await conn.fetch(
            "SELECT application_name, client_addr::text AS client_addr, state, sync_state, "
            "pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes "
            "FROM pg_stat_replication"
        )
        replicas = [dict(r) for r in rows]
        for replica in replicas:
            if replica["lag_bytes"] is not None:
                replica["lag_bytes"] = int(replica["lag_bytes"])
        return {
            "role": "primary",
            "replicas": replicas,
        }

    receiver = await conn.fetchrow(
        "SELECT status, sender_host, sender_port FROM pg_stat_wal_receiver"
    )
    last_receive_lsn = await conn.fetchval("SELECT pg_last_wal_receive_lsn()")
    last_replay_lsn = await conn.fetchval("SELECT pg_last_wal_replay_lsn()")
    lag_bytes = None
    if last_receive_lsn is not None and last_replay_lsn is not None:
        lag_bytes = await conn.fetchval(
            "SELECT pg_wal_lsn_diff($1, $2)", last_receive_lsn, last_replay_lsn
        )
        if lag_bytes is not None:
            lag_bytes = int(lag_bytes)

    return {
        "role": "standby",
        "connected_to_primary": receiver is not None,
        "sender_host": receiver["sender_host"] if receiver else None,
        "lag_bytes": lag_bytes,
    }


async def promote(conn: asyncpg.Connection, *, wait_seconds: float = 15.0) -> None:
    await conn.execute("SELECT pg_promote(wait := false)")
    elapsed = 0.0
    while elapsed < wait_seconds:
        if not await conn.fetchval("SELECT pg_is_in_recovery()"):
            return
        await asyncio.sleep(0.5)
        elapsed += 0.5
    raise RuntimeError("Promotion did not complete within the expected time")
