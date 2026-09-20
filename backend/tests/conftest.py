import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.db.session as db_session_module
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite://"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(autouse=True)
def patch_rate_limit_db_access(monkeypatch):
    """app/core/rate_limit.py's plan-lookup deliberately does a local `from
    app.db.session import AsyncSessionLocal` on every call (not a module-level
    import) since it runs inside ASGI middleware, outside FastAPI's dependency
    injection — so `app.dependency_overrides[get_db]` above never reaches it.
    Patching the attribute on `app.db.session` itself (not a copy already bound
    into some other module's namespace) is what that lazy import actually re-reads
    each time, so this is the one patch point that closes the gap: without it,
    rate limiting on every org-scoped test request would hit whatever real
    database `DATABASE_URL` in `.env` points at instead of the test database —
    invisible when that URL happened to be unreachable, a real cross-test hazard
    now that it can point at a live database for manual verification."""
    monkeypatch.setattr(db_session_module, "AsyncSessionLocal", TestSessionLocal)


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_default_plans()
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter():
    """app/core/rate_limit.py's buckets are process-global, in-memory state,
    by design (cf. its own docstring — single-process is the target deployment
    for now). Left unchecked across a whole test SESSION they'd accumulate:
    dozens of tests each doing a register+login against the same simulated
    client IP would blow through the 20/minute unauthenticated limit almost
    immediately and start 429-ing otherwise-unrelated tests. Cleared before
    every test so each one starts with a fresh window — this is a testability
    concern only, not a product behavior change."""
    from app.core.rate_limit import _buckets, _plan_cache

    _buckets.clear()
    _plan_cache.clear()
    yield


async def _seed_default_plans() -> None:
    """Tests build the schema via Base.metadata.create_all(), not Alembic, so
    the "free"/"pro" plan rows seeded by the Phase 10 migration (cf. alembic/
    versions/3889e63a4a84_phase10_billing.py) never land here on their own —
    every organization creation depends on a "free" plan existing (cf.
    app/api/v1/endpoints/organizations.py), so this has to be seeded
    explicitly for the test DB. A real regression: every single test that
    creates an organization broke with a 500 the first time this Phase 10
    check shipped, because this seeding step was missing."""
    from app.models.plan import Plan

    async with TestSessionLocal() as session:
        session.add(
            Plan(
                name="free",
                quotas={"max_databases": 1, "max_storage_gb": 20, "max_cpu_total": 1},
                pricing={"base_fee": "0"},
            )
        )
        session.add(
            Plan(
                name="pro",
                quotas={"max_databases": 10, "max_storage_gb": 200, "max_cpu_total": 16},
                pricing={"base_fee": "25.00", "cpu_hours": "0.02", "storage_gb_hours": "0.0005"},
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register_and_login(
    client: AsyncClient, email: str, password: str = "correct-horse-battery"
) -> dict:
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def promote_to_platform_admin(email: str) -> None:
    from sqlalchemy import select

    from app.models.user import User

    async with TestSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        user.is_platform_admin = True
        await session.commit()


async def register_platform_admin(
    client: AsyncClient, email: str, password: str = "correct-horse-battery"
) -> dict:
    headers = await register_and_login(client, email, password)
    await promote_to_platform_admin(email)
    return headers
