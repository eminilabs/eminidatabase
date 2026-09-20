"""Applies the tenant schema (alembic_tenant/) to one institution's database.

Run out-of-process (subprocess), not via alembic's Python API in-line: alembic's
own async env.py calls asyncio.run() internally (cf. alembic_tenant/env.py), which
cannot be nested inside this service's already-running event loop (the onboarding
job handler is itself async). A subprocess sidesteps that entirely and mirrors how
agent/app/backup.py already shells out to pg_dump/pg_restore elsewhere in this
codebase.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_MICROFINANCE_ROOT = Path(__file__).resolve().parent.parent.parent


async def run_tenant_migrations(database_url: str) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "-c",
        "alembic_tenant.ini",
        "-x",
        f"tenant_url={database_url}",
        "upgrade",
        "head",
        cwd=str(_MICROFINANCE_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(
            f"Tenant migration failed (exit {process.returncode}): "
            f"{stderr.decode(errors='replace')}\n{stdout.decode(errors='replace')}"
        )
