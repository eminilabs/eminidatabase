"""Executes the actual PostgreSQL DDL for provisioning — the only place in the
whole platform that runs CREATE/DROP DATABASE/ROLE.

cf. docs/architecture/03-database-orchestrator-et-agent.md §"Construction sécurisée
des commandes SQL": Postgres DDL has no bind-parameter support for identifiers, so
the standard, safe pattern is (1) whitelist the identifier with a strict regex
*before* it ever touches a query string, and (2) for literal values that must be
embedded in DDL (like a password), fetch a properly escaped literal via a
parametrized SELECT (asyncpg escapes the bind value; we then use that already-quoted
string) rather than formatting the raw value into SQL ourselves.
"""

from __future__ import annotations

import re

import asyncpg

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")

# Curated allowlist (cf. docs/architecture §32 — least privilege): several bundled
# extensions (plpythonu, adminpack, file_fdw...) grant filesystem or code-execution
# capability and must never be reachable through a self-service API.
ALLOWED_EXTENSIONS = frozenset(
    {"uuid-ossp", "pgcrypto", "pg_trgm", "citext", "hstore", "pg_stat_statements"}
)

# APP roles get full read/write; READONLY roles get SELECT only. ADMIN (the
# database owner) is only ever created once, at provisioning time, in
# create_database — never through the additional-role endpoints.
ROLE_SCOPES = frozenset({"app", "readonly"})


class InvalidIdentifierError(ValueError):
    pass


def validate_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise InvalidIdentifierError(f"Invalid identifier: {name!r}")
    return name


async def _quoted_literal(conn: asyncpg.Connection, value: str) -> str:
    return await conn.fetchval("SELECT quote_literal($1)", value)


async def create_database(
    conn: asyncpg.Connection, *, database_name: str, role_name: str, password: str
) -> None:
    database_name = validate_identifier(database_name)
    role_name = validate_identifier(role_name)

    quoted_password = await _quoted_literal(conn, password)
    await conn.execute(f'CREATE ROLE "{role_name}" WITH LOGIN PASSWORD {quoted_password}')
    await conn.execute(f'CREATE DATABASE "{database_name}" OWNER "{role_name}"')


async def drop_database(conn: asyncpg.Connection, *, database_name: str, role_name: str) -> None:
    database_name = validate_identifier(database_name)
    role_name = validate_identifier(role_name)

    await _terminate_connections(conn, database_name)
    await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    await conn.execute(f'DROP ROLE IF EXISTS "{role_name}"')


async def set_connection_limit(conn: asyncpg.Connection, *, database_name: str, limit: int) -> None:
    """Vertical resize's concrete, enforceable guarantee on a shared cluster
    (cf. docs/architecture/05 §5.4): databases on a shared Postgres instance don't
    get isolated CPU/RAM cgroups the way a dedicated VM/container would, so the
    resource tier is expressed as a connection budget instead. `limit` comes from
    Pydantic as an int, so it can never contain SQL syntax — safe to interpolate
    directly, unlike an identifier or a string literal."""
    database_name = validate_identifier(database_name)
    if limit < -1:
        raise ValueError("Connection limit must be -1 (unlimited) or a non-negative integer")
    await conn.execute(f'ALTER DATABASE "{database_name}" WITH CONNECTION LIMIT {int(limit)}')


async def quiesce_for_migration(
    conn: asyncpg.Connection, *, database_name: str, role_name: str
) -> None:
    """Blocks tenant connections without blocking the admin connection
    migration's own pg_dump needs a moment later — unlike suspend_database's
    ALLOW_CONNECTIONS false, which blocks *everyone*, including our own dump.

    Revoking CONNECT from just `role_name` turned out not to be enough (a second
    real bug caught by the Phase 7 test suite): PostgreSQL databases grant CONNECT
    to PUBLIC by default, so a specific role's connections keep working via that
    grant even after it's individually revoked. Revoking from PUBLIC instead blocks
    every non-superuser role at once — correct anyway, since migration should
    quiesce *all* of the tenant's roles (e.g. an additional readonly role from
    Phase 4), not just the primary one.

    That still wasn't enough on its own either (a third real bug): the tenant's
    role is this database's *owner* (cf. create_database), and ownership grants an
    implicit, unrevokable CONNECT — REVOKE has no effect on it. So ownership is
    reassigned to the connecting admin first; only then does revoking PUBLIC's
    CONNECT actually bind the former owner too. Safe here because the source is
    always dropped once migration succeeds — there's no need to hand ownership
    back.
    """
    database_name = validate_identifier(database_name)
    # role_name is validated (defense in depth against a malformed caller) even
    # though the ACL change below is broader than just this one role.
    validate_identifier(role_name)

    admin_role = await conn.fetchval("SELECT current_user")
    await conn.execute(f'ALTER DATABASE "{database_name}" OWNER TO "{admin_role}"')
    await conn.execute(f'REVOKE CONNECT ON DATABASE "{database_name}" FROM PUBLIC')
    await conn.execute(
        "SELECT pg_terminate_backend(a.pid) FROM pg_stat_activity a "
        "JOIN pg_roles r ON r.rolname = a.usename "
        "WHERE a.datname = $1 AND a.pid <> pg_backend_pid() AND NOT r.rolsuper",
        database_name,
    )


async def suspend_database(conn: asyncpg.Connection, *, database_name: str) -> None:
    database_name = validate_identifier(database_name)
    await conn.execute(f'ALTER DATABASE "{database_name}" WITH ALLOW_CONNECTIONS false')
    await _terminate_connections(conn, database_name)


async def resume_database(conn: asyncpg.Connection, *, database_name: str) -> None:
    database_name = validate_identifier(database_name)
    await conn.execute(f'ALTER DATABASE "{database_name}" WITH ALLOW_CONNECTIONS true')


async def _terminate_connections(conn: asyncpg.Connection, database_name: str) -> None:
    await conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = $1 AND pid <> pg_backend_pid()",
        database_name,
    )


async def connect_to_database(admin_dsn: str, database_name: str) -> asyncpg.Connection:
    """Some operations (GRANT, ALTER DEFAULT PRIVILEGES, CREATE EXTENSION) are
    per-database, not cluster-wide, so they must run on a connection to that exact
    database rather than the maintenance connection used for CREATE/DROP DATABASE.
    Reuses the same admin user/password/host/port, only the target db differs."""
    database_name = validate_identifier(database_name)
    return await asyncpg.connect(admin_dsn, database=database_name)


async def create_role_in_database(
    pool: asyncpg.Pool,
    admin_dsn: str,
    *,
    database_name: str,
    role_name: str,
    password: str,
    scope: str,
) -> None:
    database_name = validate_identifier(database_name)
    role_name = validate_identifier(role_name)
    if scope not in ROLE_SCOPES:
        raise ValueError(f"Unsupported role scope: {scope!r} (must be one of {ROLE_SCOPES})")

    async with pool.acquire() as conn:
        quoted_password = await _quoted_literal(conn, password)
        await conn.execute(f'CREATE ROLE "{role_name}" WITH LOGIN PASSWORD {quoted_password}')

    target_conn = await connect_to_database(admin_dsn, database_name)
    try:
        # Default privileges only ever apply to objects created *by the role named
        # in FOR ROLE* — without it, ALTER DEFAULT PRIVILEGES silently sets defaults
        # for objects the connecting (superuser) role creates, which is never who
        # actually creates a tenant's tables. The database owner is who does.
        owner_name = await target_conn.fetchval(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
        )

        await target_conn.execute(f'GRANT CONNECT ON DATABASE "{database_name}" TO "{role_name}"')
        await target_conn.execute(f'GRANT USAGE ON SCHEMA public TO "{role_name}"')
        if scope == "app":
            await target_conn.execute(f'GRANT CREATE ON SCHEMA public TO "{role_name}"')
            await target_conn.execute(
                f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{role_name}"'
            )
            await target_conn.execute(
                f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{role_name}"'
            )
            await target_conn.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner_name}" IN SCHEMA public '
                f'GRANT ALL PRIVILEGES ON TABLES TO "{role_name}"'
            )
            await target_conn.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner_name}" IN SCHEMA public '
                f'GRANT ALL PRIVILEGES ON SEQUENCES TO "{role_name}"'
            )
        else:  # readonly
            await target_conn.execute(
                f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{role_name}"'
            )
            await target_conn.execute(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner_name}" IN SCHEMA public '
                f'GRANT SELECT ON TABLES TO "{role_name}"'
            )
    finally:
        await target_conn.close()


async def drop_role_in_database(
    pool: asyncpg.Pool, admin_dsn: str, *, database_name: str, role_name: str
) -> None:
    database_name = validate_identifier(database_name)
    role_name = validate_identifier(role_name)

    target_conn = await connect_to_database(admin_dsn, database_name)
    try:
        await target_conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE usename = $1 AND pid <> pg_backend_pid()",
            role_name,
        )
        await target_conn.execute(f'DROP OWNED BY "{role_name}"')
    finally:
        await target_conn.close()

    async with pool.acquire() as conn:
        await conn.execute(f'DROP ROLE IF EXISTS "{role_name}"')


async def rotate_role_password(pool: asyncpg.Pool, *, role_name: str, new_password: str) -> None:
    role_name = validate_identifier(role_name)
    async with pool.acquire() as conn:
        quoted_password = await _quoted_literal(conn, new_password)
        await conn.execute(f'ALTER ROLE "{role_name}" WITH PASSWORD {quoted_password}')


def _validate_extension_name(name: str) -> str:
    if name not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Extension {name!r} is not on the allowed list: {sorted(ALLOWED_EXTENSIONS)}"
        )
    return name


async def list_extensions(admin_dsn: str, database_name: str) -> list[dict]:
    conn = await connect_to_database(admin_dsn, database_name)
    try:
        installed_rows = await conn.fetch("SELECT extname, extversion FROM pg_extension")
        installed = {r["extname"]: r["extversion"] for r in installed_rows}
        return [
            {"name": name, "installed": name in installed, "version": installed.get(name)}
            for name in sorted(ALLOWED_EXTENSIONS)
        ]
    finally:
        await conn.close()


async def install_extension(admin_dsn: str, database_name: str, extension_name: str) -> None:
    extension_name = _validate_extension_name(extension_name)
    conn = await connect_to_database(admin_dsn, database_name)
    try:
        await conn.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension_name}"')
    finally:
        await conn.close()


async def drop_extension(admin_dsn: str, database_name: str, extension_name: str) -> None:
    extension_name = _validate_extension_name(extension_name)
    conn = await connect_to_database(admin_dsn, database_name)
    try:
        await conn.execute(f'DROP EXTENSION IF EXISTS "{extension_name}"')
    finally:
        await conn.close()


async def get_database_metrics(conn: asyncpg.Connection, database_name: str) -> dict:
    database_name = validate_identifier(database_name)
    size_bytes = await conn.fetchval("SELECT pg_database_size($1)", database_name)
    active_connections = await conn.fetchval(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = $1", database_name
    )
    max_connections = await conn.fetchval("SHOW max_connections")
    return {
        "size_bytes": size_bytes,
        "active_connections": active_connections,
        "max_connections": int(max_connections),
    }


async def list_tables(admin_dsn: str, database_name: str) -> list[dict]:
    """Table/column/index introspection for the SQL Editor's schema browser
    (cahier des charges §35 — 'informations sur les tables', 'sur les index')."""
    conn = await connect_to_database(admin_dsn, database_name)
    try:
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        result = []
        for table in tables:
            table_name = table["table_name"]
            columns = await conn.fetch(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = $1 "
                "ORDER BY ordinal_position",
                table_name,
            )
            indexes = await conn.fetch(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = $1",
                table_name,
            )
            result.append(
                {
                    "name": table_name,
                    "columns": [
                        {
                            "name": c["column_name"],
                            "type": c["data_type"],
                            "nullable": c["is_nullable"] == "YES",
                        }
                        for c in columns
                    ],
                    "indexes": [
                        {"name": i["indexname"], "definition": i["indexdef"]} for i in indexes
                    ],
                }
            )
        return result
    finally:
        await conn.close()
