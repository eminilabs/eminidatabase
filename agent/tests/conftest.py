import os

import asyncpg
import pytest

from app.config import AgentSettings
from app.postgres_admin import create_database, drop_database

TEST_HOST = os.environ.get("POSTGRES_TEST_HOST", "127.0.0.1")
TEST_PORT = int(os.environ.get("POSTGRES_TEST_PORT", "5544"))
TEST_DSN = f"postgresql://postgres:postgres@{TEST_HOST}:{TEST_PORT}/postgres"

# A real streaming replica of TEST_DSN, if one has been bootstrapped (see
# ../README.md "High availability: setting up a real streaming replica") — used
# only by tests/test_replication.py, which skips cleanly if it's not reachable.
REPLICA_HOST = os.environ.get("POSTGRES_REPLICA_TEST_HOST", "127.0.0.1")
REPLICA_PORT = int(os.environ.get("POSTGRES_REPLICA_TEST_PORT", "5545"))
REPLICA_DSN = f"postgresql://postgres:postgres@{REPLICA_HOST}:{REPLICA_PORT}/postgres"


@pytest.fixture
async def admin_conn():
    try:
        conn = await asyncpg.connect(TEST_DSN, timeout=3)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"No local PostgreSQL reachable for integration test: {exc}")
        return
    yield conn
    await conn.close()


@pytest.fixture
async def replica_conn():
    try:
        conn = await asyncpg.connect(REPLICA_DSN, timeout=3)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"No streaming replica reachable for integration test: {exc}")
        return
    yield conn
    await conn.close()


@pytest.fixture
async def admin_pool():
    try:
        pool = await asyncpg.create_pool(TEST_DSN, min_size=1, max_size=3, timeout=3)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"No local PostgreSQL reachable for integration test: {exc}")
        return
    yield pool
    await pool.close()


@pytest.fixture
async def provisioned_database(admin_conn):
    """A real database + owner role, like Phase 3's create_database leaves behind,
    for Phase 4/5 tests to build on."""
    db_name, role_name, password = "db_test_p4_1", "u_test_p4_1", "s3cret-test-pass"
    await create_database(
        admin_conn, database_name=db_name, role_name=role_name, password=password
    )
    yield db_name, role_name, password
    await drop_database(admin_conn, database_name=db_name, role_name=role_name)


@pytest.fixture
def backup_settings() -> AgentSettings:
    """Routes pg_dump/pg_restore through `docker exec` into the same container the
    other fixtures here talk to over the host-mapped port — see agent/.env.example
    for why the prefix and the host/port fixture use different addresses."""
    return AgentSettings(
        postgres_admin_dsn=TEST_DSN,
        pg_dump_command_prefix=os.environ.get(
            "PG_DUMP_COMMAND_PREFIX", "docker,exec,-i,eminidb-node-postgres"
        ),
        pg_dump_host=os.environ.get("PG_DUMP_TEST_HOST", "127.0.0.1"),
        pg_dump_port=int(os.environ.get("PG_DUMP_TEST_PORT", "5432")),
        backup_encryption_key="08u_J80OTnrWkefxT-D4WVGWAnX-CJynJWy-T-SCvXQ=",
        s3_endpoint_url=os.environ.get("S3_TEST_ENDPOINT_URL", "http://127.0.0.1:9000"),
        s3_bucket="eminidatabase-backups-test",
    )
