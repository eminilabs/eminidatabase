"""Dynamic per-institution database connections.

Unlike the Control DB (one fixed engine, control_session.py), each institution
has its own database, provisioned by the platform (cf. §8.4) — the connection
target is only known at request time, once the institution is resolved from the
URL path. Engines are cached per database URL so repeated requests for the same
institution reuse one connection pool instead of reconnecting every time.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mf_app.models.institution import MFInstitution
from mf_app.services.secrets import decrypt_secret

_engine_cache: dict[str, AsyncEngine] = {}


def tenant_database_url(institution: MFInstitution) -> str:
    password = decrypt_secret(institution.encrypted_db_password)
    return (
        f"postgresql+asyncpg://{institution.db_username}:{password}@"
        f"{institution.db_host}:{institution.db_port}/{institution.db_name}"
    )


def get_tenant_engine(database_url: str) -> AsyncEngine:
    engine = _engine_cache.get(database_url)
    if engine is None:
        engine = create_async_engine(database_url, echo=False, future=True)
        _engine_cache[database_url] = engine
    return engine


async def tenant_session_for_institution(
    institution: MFInstitution,
) -> AsyncGenerator[AsyncSession, None]:
    engine = get_tenant_engine(tenant_database_url(institution))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session
