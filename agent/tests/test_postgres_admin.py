"""Integration tests against a real PostgreSQL instance — the actual mechanism
Phase 3 depends on, not a mock of it. Skips gracefully if none is reachable (e.g. in
an environment without Docker); see ../README.md for how to start one locally.
"""

import asyncpg
import pytest

from app.postgres_admin import (
    InvalidIdentifierError,
    create_database,
    create_role_in_database,
    drop_database,
    drop_extension,
    drop_role_in_database,
    get_database_metrics,
    install_extension,
    list_extensions,
    list_tables,
    quiesce_for_migration,
    resume_database,
    rotate_role_password,
    set_connection_limit,
    suspend_database,
    validate_identifier,
)
from tests.conftest import TEST_DSN, TEST_HOST, TEST_PORT


async def _connect_as(role_name: str, password: str, database_name: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=TEST_HOST, port=TEST_PORT, user=role_name, password=password,
        database=database_name, timeout=3,
    )


async def test_create_database_produces_working_credentials(admin_conn):
    db_name, role_name, password = "db_test_create_1", "u_test_create_1", "s3cret-test-pass"
    try:
        await create_database(
            admin_conn, database_name=db_name, role_name=role_name, password=password
        )

        exists = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name)
        assert exists == 1

        # The point of this test: the credentials the orchestrator would hand to a
        # client actually work, end to end, against a real server.
        client_conn = await _connect_as(role_name, password, db_name)
        assert await client_conn.fetchval("SELECT 1") == 1
        await client_conn.close()
    finally:
        await drop_database(admin_conn, database_name=db_name, role_name=role_name)


async def test_drop_database_removes_role_and_database(admin_conn):
    db_name, role_name, password = "db_test_drop_1", "u_test_drop_1", "s3cret-test-pass"
    await create_database(admin_conn, database_name=db_name, role_name=role_name, password=password)

    await drop_database(admin_conn, database_name=db_name, role_name=role_name)

    db_exists = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name)
    role_exists = await admin_conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role_name)
    assert db_exists is None
    assert role_exists is None


async def test_suspend_blocks_new_connections_and_resume_restores_them(admin_conn):
    db_name, role_name, password = "db_test_suspend_1", "u_test_suspend_1", "s3cret-test-pass"
    await create_database(admin_conn, database_name=db_name, role_name=role_name, password=password)
    try:
        await suspend_database(admin_conn, database_name=db_name)
        with pytest.raises(asyncpg.PostgresError):
            await _connect_as(role_name, password, db_name)

        await resume_database(admin_conn, database_name=db_name)
        conn = await _connect_as(role_name, password, db_name)
        assert await conn.fetchval("SELECT 1") == 1
        await conn.close()
    finally:
        await drop_database(admin_conn, database_name=db_name, role_name=role_name)


def test_validate_identifier_rejects_injection_attempts():
    for malicious in ['"; DROP TABLE users; --', "db name", "db-name", "DB_NAME", "", "a"]:
        with pytest.raises(InvalidIdentifierError):
            validate_identifier(malicious)


def test_validate_identifier_accepts_normal_names():
    assert validate_identifier("db_abc123") == "db_abc123"


async def test_readonly_role_can_select_but_not_insert(admin_pool, provisioned_database):
    db_name, _owner_role, _owner_password = provisioned_database
    role_name, password = "u_test_ro_1", "s3cret-readonly-pass"

    await create_role_in_database(
        admin_pool, TEST_DSN, database_name=db_name, role_name=role_name,
        password=password, scope="readonly",
    )
    try:
        owner_conn = await asyncpg.connect(
            host=TEST_HOST, port=TEST_PORT, user=_owner_role, password=_owner_password,
            database=db_name, timeout=3,
        )
        await owner_conn.execute("CREATE TABLE items (id serial primary key, label text)")
        await owner_conn.execute("INSERT INTO items (label) VALUES ('seed')")
        await owner_conn.close()

        ro_conn = await asyncpg.connect(
            host=TEST_HOST, port=TEST_PORT, user=role_name, password=password,
            database=db_name, timeout=3,
        )
        rows = await ro_conn.fetch("SELECT * FROM items")
        assert len(rows) == 1

        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await ro_conn.execute("INSERT INTO items (label) VALUES ('blocked')")
        await ro_conn.close()
    finally:
        await drop_role_in_database(
            admin_pool, TEST_DSN, database_name=db_name, role_name=role_name
        )


async def test_app_scope_role_can_write(admin_pool, provisioned_database):
    db_name, _owner_role, _owner_password = provisioned_database
    role_name, password = "u_test_rw_1", "s3cret-readwrite-pass"

    await create_role_in_database(
        admin_pool, TEST_DSN, database_name=db_name, role_name=role_name,
        password=password, scope="app",
    )
    try:
        conn = await asyncpg.connect(
            host=TEST_HOST, port=TEST_PORT, user=role_name, password=password,
            database=db_name, timeout=3,
        )
        await conn.execute("CREATE TABLE widgets (id serial primary key)")
        await conn.execute("INSERT INTO widgets DEFAULT VALUES")
        assert await conn.fetchval("SELECT count(*) FROM widgets") == 1
        await conn.close()
    finally:
        await drop_role_in_database(
            admin_pool, TEST_DSN, database_name=db_name, role_name=role_name
        )


async def test_rotate_role_password_changes_credential(admin_pool, provisioned_database):
    db_name, _owner_role, _owner_password = provisioned_database
    role_name, password = "u_test_rot_1", "s3cret-original-pass"

    await create_role_in_database(
        admin_pool, TEST_DSN, database_name=db_name, role_name=role_name,
        password=password, scope="readonly",
    )
    try:
        new_password = "s3cret-rotated-pass"
        await rotate_role_password(admin_pool, role_name=role_name, new_password=new_password)

        with pytest.raises(asyncpg.InvalidPasswordError):
            await asyncpg.connect(
                host=TEST_HOST, port=TEST_PORT, user=role_name, password=password,
                database=db_name, timeout=3,
            )

        conn = await asyncpg.connect(
            host=TEST_HOST, port=TEST_PORT, user=role_name, password=new_password,
            database=db_name, timeout=3,
        )
        await conn.close()
    finally:
        await drop_role_in_database(
            admin_pool, TEST_DSN, database_name=db_name, role_name=role_name
        )


async def test_install_and_drop_extension(provisioned_database):
    db_name, _owner_role, _owner_password = provisioned_database

    await install_extension(TEST_DSN, db_name, "pgcrypto")
    extensions = await list_extensions(TEST_DSN, db_name)
    pgcrypto = next(e for e in extensions if e["name"] == "pgcrypto")
    assert pgcrypto["installed"] is True

    await drop_extension(TEST_DSN, db_name, "pgcrypto")
    extensions = await list_extensions(TEST_DSN, db_name)
    pgcrypto = next(e for e in extensions if e["name"] == "pgcrypto")
    assert pgcrypto["installed"] is False


async def test_install_extension_rejects_non_allowlisted_name(provisioned_database):
    db_name, _owner_role, _owner_password = provisioned_database
    with pytest.raises(ValueError, match="not on the allowed list"):
        await install_extension(TEST_DSN, db_name, "plpythonu")


async def test_get_database_metrics_reports_size_and_connections(admin_conn, provisioned_database):
    db_name, owner_role, owner_password = provisioned_database

    conn = await asyncpg.connect(
        host=TEST_HOST, port=TEST_PORT, user=owner_role, password=owner_password,
        database=db_name, timeout=3,
    )
    try:
        metrics = await get_database_metrics(admin_conn, db_name)
        assert metrics["size_bytes"] > 0
        assert metrics["active_connections"] >= 1
        assert metrics["max_connections"] > 0
    finally:
        await conn.close()


async def test_list_tables_reports_columns_and_indexes(provisioned_database):
    db_name, owner_role, owner_password = provisioned_database

    conn = await asyncpg.connect(
        host=TEST_HOST, port=TEST_PORT, user=owner_role, password=owner_password,
        database=db_name, timeout=3,
    )
    await conn.execute(
        "CREATE TABLE customers (id serial primary key, email text unique not null)"
    )
    await conn.close()

    tables = await list_tables(TEST_DSN, db_name)
    customers = next(t for t in tables if t["name"] == "customers")
    column_names = {c["name"] for c in customers["columns"]}
    assert {"id", "email"} <= column_names
    assert len(customers["indexes"]) >= 1  # primary key + unique constraint indexes


async def test_set_connection_limit_is_enforced(admin_conn, provisioned_database):
    db_name, role_name, password = provisioned_database

    await set_connection_limit(admin_conn, database_name=db_name, limit=1)
    reported = await admin_conn.fetchval(
        "SELECT datconnlimit FROM pg_database WHERE datname = $1", db_name
    )
    assert reported == 1

    first = await _connect_as(role_name, password, db_name)
    try:
        with pytest.raises(asyncpg.TooManyConnectionsError):
            await _connect_as(role_name, password, db_name)
    finally:
        await first.close()

    await set_connection_limit(admin_conn, database_name=db_name, limit=-1)
    reported = await admin_conn.fetchval(
        "SELECT datconnlimit FROM pg_database WHERE datname = $1", db_name
    )
    assert reported == -1


async def test_set_connection_limit_rejects_invalid_value():
    # Validated before the connection is ever touched, so a real connection isn't
    # needed here — passing None makes that guarantee explicit.
    with pytest.raises(ValueError, match="Connection limit"):
        await set_connection_limit(None, database_name="db_whatever123", limit=-2)


async def test_quiesce_blocks_tenant_but_not_admin(admin_conn, provisioned_database):
    """Regression test for a real Phase 7 bug: migration used to call
    suspend_database (ALLOW_CONNECTIONS false) to quiesce the source, which also
    locked out the admin connection migration's own pg_dump needs — the dump
    failed with "not currently accepting connections" every time. quiesce_for_migration
    must block only the tenant role."""
    db_name, role_name, password = provisioned_database

    await quiesce_for_migration(admin_conn, database_name=db_name, role_name=role_name)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _connect_as(role_name, password, db_name)

    # The admin connection must still work — this is the whole point.
    still_admin = await admin_conn.fetchval("SELECT 1")
    assert still_admin == 1
