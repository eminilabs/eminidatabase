import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException

from app.backup import create_encrypted_backup, restore_encrypted_backup, verify_encrypted_backup
from app.config import get_agent_settings
from app.control_plane_client import ensure_registered, heartbeat_loop
from app.object_storage import delete_object, download_bytes, ensure_bucket, upload_bytes
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
from app.replication import get_replication_status, promote
from app.resources import collect_capacity, collect_usage
from app.schemas import (
    BackupRequest,
    BackupResponse,
    CreateRoleRequest,
    InstallExtensionRequest,
    ProvisionDatabaseRequest,
    ProvisionDatabaseResponse,
    QuiesceRequest,
    RestoreRequest,
    RotateRoleRequest,
    SetConnectionLimitRequest,
    VerifyBackupRequest,
    VerifyBackupResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

settings = get_agent_settings()

_pg_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _pg_pool
    state = ensure_registered(settings)
    logger.info("agent identity: node_id=%s hostname=%s", state.node_id, state.hostname)
    heartbeat_task = asyncio.create_task(heartbeat_loop(settings, state))

    _pg_pool = await asyncpg.create_pool(settings.postgres_admin_dsn, min_size=1, max_size=5)
    logger.info("connected to local PostgreSQL admin pool")

    await ensure_bucket(settings)
    logger.info("object storage bucket ready: %s", settings.s3_bucket)
    try:
        yield
    finally:
        heartbeat_task.cancel()
        if _pg_pool is not None:
            await _pg_pool.close()


app = FastAPI(
    title="eminidatabase Data Plane Agent",
    description=(
        "Runs on every node. Exposed only to the Control Plane over mTLS — "
        "never on a public interface."
    ),
    version=settings.agent_version,
    lifespan=lifespan,
)


def _pool() -> asyncpg.Pool:
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool not initialized")
    return _pg_pool


@app.get("/v1/health")
async def health() -> dict:
    return {
        "status": "ok",
        "hostname": settings.resolved_hostname(),
        "version": settings.agent_version,
    }


@app.get("/v1/resources")
async def resources() -> dict:
    return {**collect_capacity(), **collect_usage()}


@app.post("/v1/provision/database", response_model=ProvisionDatabaseResponse)
async def provision_database(payload: ProvisionDatabaseRequest) -> ProvisionDatabaseResponse:
    try:
        async with _pool().acquire() as conn:
            await create_database(
                conn,
                database_name=payload.database_name,
                role_name=payload.role_name,
                password=payload.password,
            )
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncpg.DuplicateDatabaseError:
        pass  # already exists — provisioning is idempotent on retry
    return ProvisionDatabaseResponse(status="created", database_name=payload.database_name)


@app.delete("/v1/database/{database_name}")
async def delete_database_endpoint(database_name: str, role_name: str) -> dict:
    try:
        async with _pool().acquire() as conn:
            await drop_database(conn, database_name=database_name, role_name=role_name)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "deleted", "database_name": database_name}


@app.post("/v1/database/{database_name}/suspend")
async def suspend_database_endpoint(database_name: str) -> dict:
    try:
        validate_identifier(database_name)
        async with _pool().acquire() as conn:
            await suspend_database(conn, database_name=database_name)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "suspended", "database_name": database_name}


@app.post("/v1/database/{database_name}/resume")
async def resume_database_endpoint(database_name: str) -> dict:
    try:
        validate_identifier(database_name)
        async with _pool().acquire() as conn:
            await resume_database(conn, database_name=database_name)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "running", "database_name": database_name}


@app.post("/v1/database/{database_name}/connection-limit")
async def set_connection_limit_endpoint(
    database_name: str, payload: SetConnectionLimitRequest
) -> dict:
    try:
        async with _pool().acquire() as conn:
            await set_connection_limit(conn, database_name=database_name, limit=payload.limit)
    except (InvalidIdentifierError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "resized", "database_name": database_name, "connection_limit": payload.limit}


@app.post("/v1/database/{database_name}/quiesce")
async def quiesce_endpoint(database_name: str, payload: QuiesceRequest) -> dict:
    try:
        async with _pool().acquire() as conn:
            await quiesce_for_migration(
                conn, database_name=database_name, role_name=payload.role_name
            )
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "quiesced", "database_name": database_name}


@app.post("/v1/database/{database_name}/roles", status_code=201)
async def create_role_endpoint(database_name: str, payload: CreateRoleRequest) -> dict:
    try:
        await create_role_in_database(
            _pool(),
            settings.postgres_admin_dsn,
            database_name=database_name,
            role_name=payload.role_name,
            password=payload.password,
            scope=payload.scope,
        )
    except (InvalidIdentifierError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "created", "role_name": payload.role_name}


@app.delete("/v1/database/{database_name}/roles/{role_name}")
async def delete_role_endpoint(database_name: str, role_name: str) -> dict:
    try:
        await drop_role_in_database(
            _pool(), settings.postgres_admin_dsn, database_name=database_name, role_name=role_name
        )
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "deleted", "role_name": role_name}


@app.post("/v1/database/{database_name}/roles/{role_name}/rotate")
async def rotate_role_endpoint(
    database_name: str, role_name: str, payload: RotateRoleRequest
) -> dict:
    try:
        validate_identifier(database_name)
        await rotate_role_password(_pool(), role_name=role_name, new_password=payload.password)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "rotated", "role_name": role_name}


@app.get("/v1/database/{database_name}/extensions")
async def list_extensions_endpoint(database_name: str) -> list[dict]:
    try:
        return await list_extensions(settings.postgres_admin_dsn, database_name)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/database/{database_name}/extensions")
async def install_extension_endpoint(
    database_name: str, payload: InstallExtensionRequest
) -> dict:
    try:
        await install_extension(settings.postgres_admin_dsn, database_name, payload.name)
    except (InvalidIdentifierError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "installed", "name": payload.name}


@app.delete("/v1/database/{database_name}/extensions/{extension_name}")
async def drop_extension_endpoint(database_name: str, extension_name: str) -> dict:
    try:
        await drop_extension(settings.postgres_admin_dsn, database_name, extension_name)
    except (InvalidIdentifierError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "dropped", "name": extension_name}


@app.get("/v1/database/{database_name}/metrics")
async def metrics_endpoint(database_name: str) -> dict:
    try:
        async with _pool().acquire() as conn:
            return await get_database_metrics(conn, database_name)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/database/{database_name}/tables")
async def tables_endpoint(database_name: str) -> list[dict]:
    try:
        return await list_tables(settings.postgres_admin_dsn, database_name)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/database/{database_name}/backup", response_model=BackupResponse)
async def backup_endpoint(database_name: str, payload: BackupRequest) -> BackupResponse:
    try:
        encrypted = await create_encrypted_backup(settings, database_name)
    except (InvalidIdentifierError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await upload_bytes(settings, payload.storage_key, encrypted)
    return BackupResponse(
        status="completed", storage_key=payload.storage_key, size_bytes=len(encrypted)
    )


@app.post("/v1/database/{database_name}/restore", response_model=ProvisionDatabaseResponse)
async def restore_endpoint(
    database_name: str, payload: RestoreRequest
) -> ProvisionDatabaseResponse:
    try:
        async with _pool().acquire() as conn:
            await create_database(
                conn,
                database_name=database_name,
                role_name=payload.role_name,
                password=payload.password,
            )
        encrypted = await download_bytes(settings, payload.storage_key)
        await restore_encrypted_backup(
            settings, database_name, encrypted, owner_role=payload.role_name
        )
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncpg.DuplicateDatabaseError:
        pass  # already provisioned — restore is idempotent on retry
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Restore failed: {exc}") from exc
    return ProvisionDatabaseResponse(status="restored", database_name=database_name)


@app.post("/v1/verify-backup", response_model=VerifyBackupResponse)
async def verify_backup_endpoint(payload: VerifyBackupRequest) -> VerifyBackupResponse:
    encrypted = await download_bytes(settings, payload.storage_key)
    result = await verify_encrypted_backup(_pool(), settings, encrypted)
    return VerifyBackupResponse(**result)


@app.delete("/v1/backups")
async def delete_backup_object_endpoint(storage_key: str) -> dict:
    await delete_object(settings, storage_key)
    return {"status": "deleted", "storage_key": storage_key}


@app.get("/v1/replication/status")
async def replication_status_endpoint() -> dict:
    async with _pool().acquire() as conn:
        return await get_replication_status(conn)


@app.post("/v1/replication/promote")
async def promote_endpoint() -> dict:
    async with _pool().acquire() as conn:
        try:
            await promote(conn)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "promoted"}
