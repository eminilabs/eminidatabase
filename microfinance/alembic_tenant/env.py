"""Migrates the TENANT schema (branches, agents, customers, accounts, loans,
ledger — cf. docs/architecture/08 §8.5/§8.6) — a different database every time,
unlike alembic_control/env.py which always targets the same Control DB. The
target is passed with `-x tenant_url=<url>` (app/services/tenant_migrate.py does
this for every institution); a local SQLite file is used as a fallback purely so
`alembic revision --autogenerate` has something to introspect against during
development.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from mf_app.db.tenant_base import TenantBase
from mf_app.db.types import GUID
from mf_app.models.tenant import *  # noqa: F401,F403 — registers all tenant models on the Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

x_args = context.get_x_argument(as_dictionary=True)
tenant_url = x_args.get("tenant_url", "sqlite+aiosqlite:///./tenant_dev.db")
config.set_main_option("sqlalchemy.url", tenant_url)

target_metadata = TenantBase.metadata


def render_item(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, GUID):
        autogen_context.imports.add("import mf_app.db.types")
        return "mf_app.db.types.GUID()"
    return False


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_item=render_item)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
