"""Integration tests against real PostgreSQL + real pg_dump/pg_restore (via the
`docker exec` bridge documented in .env.example) + real MinIO. Skips gracefully if
any of these aren't reachable rather than failing the suite."""

import uuid

import asyncpg
import pytest

from app.backup import create_encrypted_backup, restore_encrypted_backup, verify_encrypted_backup
from app.object_storage import delete_object, download_bytes, ensure_bucket, upload_bytes
from app.postgres_admin import connect_to_database
from tests.conftest import TEST_DSN, TEST_HOST, TEST_PORT


@pytest.fixture(autouse=True)
async def _require_docker_pg_dump(backup_settings):
    """dump_database shells out to `docker exec ... pg_dump`; skip cleanly if that
    isn't available in this environment instead of failing every test in the file."""
    import shutil

    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available — cannot exercise pg_dump via docker exec")


@pytest.fixture
async def object_storage_ready(backup_settings):
    try:
        await ensure_bucket(backup_settings)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No S3-compatible storage reachable for integration test: {exc}")


async def test_backup_and_restore_round_trip(
    admin_conn, admin_pool, provisioned_database, backup_settings, object_storage_ready
):
    db_name, role_name, password = provisioned_database

    seed_conn = await asyncpg.connect(
        host=TEST_HOST, port=TEST_PORT, user=role_name, password=password,
        database=db_name, timeout=3,
    )
    await seed_conn.execute("CREATE TABLE orders (id serial primary key, total numeric)")
    await seed_conn.execute("INSERT INTO orders (total) VALUES (9.99), (19.99)")
    await seed_conn.close()

    encrypted = await create_encrypted_backup(backup_settings, db_name)
    assert len(encrypted) > 0

    storage_key = f"test/{uuid.uuid4().hex}.dump.enc"
    await upload_bytes(backup_settings, storage_key, encrypted)
    try:
        downloaded = await download_bytes(backup_settings, storage_key)
        assert downloaded == encrypted

        restore_target = f"db_restore_{uuid.uuid4().hex[:16]}"
        restore_role = f"u_restore_{uuid.uuid4().hex[:16]}"
        restore_password = "s3cret-restore-pass"
        await admin_conn.execute(
            f'CREATE ROLE "{restore_role}" WITH LOGIN PASSWORD \'{restore_password}\''
        )
        await admin_conn.execute(f'CREATE DATABASE "{restore_target}" OWNER "{restore_role}"')
        try:
            await restore_encrypted_backup(
                backup_settings, restore_target, downloaded, owner_role=restore_role
            )

            # Regression check: connect as the *tenant role*, not the admin — a
            # prior bug left restored tables owned by the admin, so the tenant
            # got "permission denied" on its own data.
            tenant_conn = await asyncpg.connect(
                host=TEST_HOST, port=TEST_PORT, user=restore_role, password=restore_password,
                database=restore_target, timeout=3,
            )
            try:
                rows = await tenant_conn.fetch("SELECT total FROM orders ORDER BY id")
                await tenant_conn.execute("INSERT INTO orders (total) VALUES (5.00)")
            finally:
                await tenant_conn.close()
            assert [float(r["total"]) for r in rows] == [9.99, 19.99]
        finally:
            await admin_conn.execute(
                f'DROP DATABASE IF EXISTS "{restore_target}" WITH (FORCE)'
            )
            await admin_conn.execute(f'DROP ROLE IF EXISTS "{restore_role}"')
    finally:
        await delete_object(backup_settings, storage_key)


async def test_verify_encrypted_backup_reports_success_for_good_backup(
    admin_pool, provisioned_database, backup_settings
):
    db_name, role_name, password = provisioned_database

    conn = await connect_to_database(TEST_DSN, db_name)
    await conn.execute("CREATE TABLE products (id serial primary key, name text)")
    await conn.execute("INSERT INTO products (name) VALUES ('widget')")
    await conn.close()

    encrypted = await create_encrypted_backup(backup_settings, db_name)
    result = await verify_encrypted_backup(admin_pool, backup_settings, encrypted)

    assert result["verified"] is True
    assert "table" in result["detail"]


async def test_verify_encrypted_backup_reports_failure_for_corrupt_backup(
    admin_pool, backup_settings
):
    result = await verify_encrypted_backup(admin_pool, backup_settings, b"not a real backup")
    assert result["verified"] is False
