"""Integration tests against the real primary + streaming replica pair described
in ../README.md. Skip cleanly if the replica hasn't been bootstrapped.
"""

import asyncio
import os

import pytest

from app.replication import get_replication_status, promote


async def test_primary_reports_role_and_connected_replica(admin_conn):
    status = await get_replication_status(admin_conn)
    assert status["role"] == "primary"
    assert any(r["application_name"] == "walreceiver" for r in status["replicas"])
    assert isinstance(status["replicas"][0]["lag_bytes"], int)


async def test_replica_reports_standby_role(replica_conn):
    status = await get_replication_status(replica_conn)
    assert status["role"] == "standby"
    assert status["connected_to_primary"] is True
    assert isinstance(status["lag_bytes"], int)


async def test_data_written_on_primary_replicates_to_standby(admin_conn, replica_conn):
    await admin_conn.execute("CREATE DATABASE ha_replication_test")
    try:
        await asyncio.sleep(0.5)  # DDL on a fresh DB still needs a beat to stream
        exists = await replica_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'ha_replication_test'"
        )
        assert exists == 1
    finally:
        await admin_conn.execute("DROP DATABASE ha_replication_test")


@pytest.mark.skipif(
    os.environ.get("RUN_DESTRUCTIVE_HA_TESTS") != "1",
    reason=(
        "Promotion permanently detaches the replica from the primary — it would "
        "have to be re-bootstrapped (pg_basebackup) afterward. Opt in explicitly "
        "with RUN_DESTRUCTIVE_HA_TESTS=1; the live Phase 6 smoke test exercises "
        "this path deliberately instead."
    ),
)
async def test_promote_replica_becomes_writable_primary(replica_conn):
    await promote(replica_conn)
    status = await get_replication_status(replica_conn)
    assert status["role"] == "primary"

    # A promoted node must accept writes — it wasn't just relabeled.
    await replica_conn.execute("CREATE DATABASE post_promotion_check")
    await replica_conn.execute("DROP DATABASE post_promotion_check")
