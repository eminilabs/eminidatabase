"""pg_dump/pg_restore execution, encryption, and the throwaway-database restore
used both for real restores and for backup verification.

cf. docs/architecture/05-backup-ha-scaling.md — backups are encrypted before they
leave this process (never stored in plaintext, cf. Règle 15) and a restore always
targets a brand-new database, never overwrites one in place.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
from cryptography.fernet import Fernet

from app.config import AgentSettings
from app.postgres_admin import connect_to_database, validate_identifier


def _fernet(settings: AgentSettings) -> Fernet:
    return Fernet(settings.backup_encryption_key.encode())


async def _run(cmd: list[str], *, env: dict, input_bytes: bytes | None = None) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate(input=input_bytes)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{cmd[0]} exited {proc.returncode}: {stderr.decode(errors='replace')[:2000]}"
        )
    return stdout


async def dump_database(settings: AgentSettings, database_name: str) -> bytes:
    database_name = validate_identifier(database_name)
    admin_user, admin_password = settings.admin_credentials()
    cmd = [
        *settings.dump_command_prefix(),
        settings.pg_dump_path,
        "-h", settings.pg_dump_host,
        "-p", str(settings.pg_dump_port),
        "-U", admin_user,
        "-Fc",
        database_name,
    ]
    return await _run(cmd, env={**os.environ, "PGPASSWORD": admin_password})


async def restore_dump(
    settings: AgentSettings, database_name: str, dump_bytes: bytes, *, owner_role: str | None = None
) -> None:
    """`--role` matters: without it, `--no-owner` still leaves every restored
    object owned by whichever role pg_restore's session runs as (the connecting
    admin), not the database's actual tenant role — the tenant would then get
    "permission denied" on its own tables. Passing the tenant's role here makes
    pg_restore SET ROLE before creating each object, so ownership ends up where a
    freshly-created database would have put it. The admin is a superuser, so it
    can SET ROLE to any role without needing explicit membership. Verification
    (owner_role left as None) doesn't care, since it only ever checks via the
    admin connection itself."""
    database_name = validate_identifier(database_name)
    admin_user, admin_password = settings.admin_credentials()
    target_role = owner_role or admin_user
    cmd = [
        *settings.dump_command_prefix(),
        settings.pg_restore_path,
        "-h", settings.pg_dump_host,
        "-p", str(settings.pg_dump_port),
        "-U", admin_user,
        "-d", database_name,
        "--no-owner",
        f"--role={target_role}",
    ]
    await _run(cmd, env={**os.environ, "PGPASSWORD": admin_password}, input_bytes=dump_bytes)


async def create_encrypted_backup(settings: AgentSettings, database_name: str) -> bytes:
    raw = await dump_database(settings, database_name)
    return _fernet(settings).encrypt(raw)


async def restore_encrypted_backup(
    settings: AgentSettings,
    database_name: str,
    encrypted_bytes: bytes,
    *,
    owner_role: str | None = None,
) -> None:
    raw = _fernet(settings).decrypt(encrypted_bytes)
    await restore_dump(settings, database_name, raw, owner_role=owner_role)


async def verify_encrypted_backup(
    pool: asyncpg.Pool, settings: AgentSettings, encrypted_bytes: bytes
) -> dict:
    """Restores into a disposable database, sanity-checks it, then drops it —
    cahier des charges §59: a backup isn't trustworthy just because it was made."""
    temp_db = f"verify_{uuid.uuid4().hex[:16]}"
    async with pool.acquire() as conn:
        await conn.execute(f'CREATE DATABASE "{temp_db}"')

    try:
        raw = _fernet(settings).decrypt(encrypted_bytes)
        await restore_dump(settings, temp_db, raw)

        check_conn = await connect_to_database(settings.postgres_admin_dsn, temp_db)
        try:
            table_count = await check_conn.fetchval(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
        finally:
            await check_conn.close()

        return {"verified": True, "detail": f"Restored successfully; {table_count} table(s) found"}
    except Exception as exc:  # noqa: BLE001 — reporting verification failure, not crashing
        return {"verified": False, "detail": str(exc)[:2000]}
    finally:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP DATABASE IF EXISTS "{temp_db}" WITH (FORCE)')
