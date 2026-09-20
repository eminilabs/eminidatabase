"""Runs the microfinance service against the REAL backend Control Plane app,
in-process (ASGITransport) — this is what proves the dogfooding claim of
docs/architecture/08 §8.3 in automated tests, not just in a manual live smoke
test: every institution onboarded in these tests goes through the real
eminidatabase_sdk.PlatformClient, hitting real backend routing/validation/DB,
exactly like backend/tests/conftest.py's own suite and sdk/tests/conftest.py.

`backend/` uses the top-level package name `app`; this service also uses `app`
as its own top-level name INTERNALLY in every other repo, so it was renamed to
`mf_app` specifically so both can be imported in the same test process without
colliding — the exact same class of bug Phase 8 found with the `tests` package
name (see sdk/README.md's Test section).

Two things are deliberately faked, matching the project-wide precedent (every
other phase's automated suite mocks the agent, real Docker Postgres is reserved
for a manual, documented live-verification pass — cf. docs/architecture/09):
- `app.services.orchestrator.call_agent` (backend) — no real Data Plane Agent/
  Postgres for the *platform's own* database provisioning.
- `mf_app.db.tenant_session.tenant_database_url` — returns a real local SQLite
  file instead of a `postgresql+asyncpg://` URL, so the actual tenant Alembic
  migration subprocess still genuinely runs against a real database file, it's
  just not Postgres.
"""

import os
import sys
from pathlib import Path

from argon2 import PasswordHasher

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# mf_app.core.config.get_settings() is @lru_cache'd — it must see the operator
# token hash the FIRST time anything imports mf_app.main (which reads settings at
# module level), so this has to happen before that import, not inside a fixture.
MF_OPERATOR_TOKEN = "test-operator-token-plaintext"
os.environ["MF_OPERATOR_TOKEN_HASH"] = PasswordHasher().hash(MF_OPERATOR_TOKEN)

import app.worker as backend_worker_module  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.db.base import Base as BackendBase  # noqa: E402
from app.db.session import get_db as backend_get_db  # noqa: E402
from app.main import app as backend_app  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import mf_app.worker as mf_worker_module  # noqa: E402
from mf_app.db.control_base import ControlBase  # noqa: E402
from mf_app.db.control_session import get_control_db  # noqa: E402
from mf_app.main import app as mf_app_instance  # noqa: E402

BACKEND_TEST_DATABASE_URL = "sqlite+aiosqlite://"
backend_test_engine = create_async_engine(
    BACKEND_TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
BackendTestSessionLocal = async_sessionmaker(
    bind=backend_test_engine, expire_on_commit=False, autoflush=False
)


async def _override_backend_get_db():
    async with BackendTestSessionLocal() as session:
        yield session


backend_app.dependency_overrides[backend_get_db] = _override_backend_get_db

CONTROL_TEST_DATABASE_URL = "sqlite+aiosqlite://"
control_test_engine = create_async_engine(
    CONTROL_TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
ControlTestSessionLocal = async_sessionmaker(
    bind=control_test_engine, expire_on_commit=False, autoflush=False
)


async def _override_get_control_db():
    async with ControlTestSessionLocal() as session:
        yield session


mf_app_instance.dependency_overrides[get_control_db] = _override_get_control_db


@pytest_asyncio.fixture(autouse=True)
async def prepare_databases():
    async with backend_test_engine.begin() as conn:
        await conn.run_sync(BackendBase.metadata.create_all)
    async with control_test_engine.begin() as conn:
        await conn.run_sync(ControlBase.metadata.create_all)
    yield
    async with backend_test_engine.begin() as conn:
        await conn.run_sync(BackendBase.metadata.drop_all)
    async with control_test_engine.begin() as conn:
        await conn.run_sync(ControlBase.metadata.drop_all)


@pytest.fixture
def backend_transport() -> ASGITransport:
    return ASGITransport(app=backend_app)


@pytest_asyncio.fixture
async def mf_client(backend_transport, monkeypatch, tmp_path):
    """An httpx client hitting the microfinance API in-process, with the SDK
    calls it makes internally routed to the in-process backend instead of real
    HTTP, and tenant migrations routed to a real local SQLite file per
    institution instead of a real Postgres (cf. module docstring)."""
    import eminidatabase_sdk.client as sdk_client_module

    original_init = sdk_client_module.PlatformClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = backend_transport
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(sdk_client_module.PlatformClient, "__init__", patched_init)

    def _fake_tenant_url(institution):
        return f"sqlite+aiosqlite:///{tmp_path}/{institution.id}.db"

    monkeypatch.setattr("mf_app.db.tenant_session.tenant_database_url", _fake_tenant_url)
    monkeypatch.setattr("mf_app.services.onboarding.tenant_database_url", _fake_tenant_url)

    transport = ASGITransport(app=mf_app_instance)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
        yield client


@pytest.fixture
def backend_db_session_factory():
    return BackendTestSessionLocal


@pytest.fixture
def control_db_session_factory():
    return ControlTestSessionLocal


@pytest.fixture
def backend_worker(monkeypatch):
    # app.worker.run_once() bypasses FastAPI's dependency system entirely — it
    # imports app.db.session.AsyncSessionLocal directly, which defaults to a real
    # on-disk SQLite file, not the in-memory test engine the HTTP dependency
    # override above points at. Same fix sdk/tests/test_client.py already needed.
    monkeypatch.setattr(backend_worker_module, "AsyncSessionLocal", BackendTestSessionLocal)
    return backend_worker_module


@pytest.fixture
def mf_worker(monkeypatch):
    monkeypatch.setattr(mf_worker_module, "AsyncSessionLocal", ControlTestSessionLocal)
    return mf_worker_module


@pytest.fixture
def run_onboarding_job(backend_worker, mf_worker, monkeypatch):
    """Runs the onboard_institution MFJob to completion.

    The job handler (mf_app/services/onboarding.py) calls the real backend's
    create_database, then the SDK's wait_for_job — which polls over real HTTP.
    Nothing else advances the backend's OWN job queue while that poll loop runs
    (this is a single test process, not two live services), so PlatformClient.
    wait_for_job is patched to tick backend_worker.run_once() between polls.

    A first version of this fixture used a separate asyncio.Task running
    backend_worker.run_once() concurrently with the poll loop instead — a real
    bug: sqlite+aiosqlite's in-memory StaticPool engine shares exactly ONE
    underlying connection across every session, and interleaving two AsyncSession
    transactions on it from two concurrently-scheduled coroutines intermittently
    raised `OperationalError: cannot commit transaction - SQL statements in
    progress` (only under Phase 9.2's heavier test load — more onboarded
    institutions per run made the race far more likely to actually land).
    Ticking the worker synchronously, in the same coroutine, right inside the
    polling loop removes the race entirely instead of narrowing its window.
    """
    import eminidatabase_sdk.client as sdk_client_module

    async def _patched_wait_for_job(self, job_id, *, interval=1.0, timeout=120.0):
        import time

        start = time.monotonic()
        while True:
            job = await self.get_job(job_id)
            if job["status"] in {"succeeded", "failed"}:
                return job
            await backend_worker.run_once()
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    monkeypatch.setattr(sdk_client_module.PlatformClient, "wait_for_job", _patched_wait_for_job)

    return mf_worker.run_once


async def fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
    class _Resp:
        def json(self_inner):
            return {"status": "ok"}

    return _Resp()


@pytest.fixture(autouse=True)
def patch_backend_agent(monkeypatch):
    monkeypatch.setattr("app.services.orchestrator.call_agent", fake_call_agent)


@pytest_asyncio.fixture(autouse=True)
async def dispose_tenant_engines():
    """mf_app.db.tenant_session._engine_cache is a process-level dict that never
    disposes an engine on its own (by design — a real deployment keeps one
    connection pool per institution for its whole lifetime). Left unchecked
    across a whole test session, every institution onboarded (5+ across this
    suite) leaves an aiosqlite engine, and each aiosqlite connection owns a
    background thread — accumulating enough of them was observed to make the
    interpreter hang on shutdown after the last test. Each test's institutions
    are unique (tmp_path-scoped) anyway, so nothing needs to survive past it."""
    import mf_app.db.tenant_session as tenant_session_module

    yield
    for engine in tenant_session_module._engine_cache.values():
        await engine.dispose()
    tenant_session_module._engine_cache.clear()


@pytest.fixture
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {MF_OPERATOR_TOKEN}"}


@pytest_asyncio.fixture
async def platform_account(backend_transport, control_db_session_factory):
    """Bootstraps the microfinance service's single Control Plane identity —
    the automated-test equivalent of scripts/bootstrap_platform_account.py:
    register + login + create_organization for real against the in-process
    backend, then persist the resulting MFPlatformAccount row."""
    from mf_app.models.platform_account import MFPlatformAccount
    from mf_app.services.secrets import encrypt_secret

    email, password = "mf-service@example.com", "correct-horse-battery"
    async with AsyncClient(transport=backend_transport, base_url="http://test/api/v1") as bc:
        await bc.post("/auth/register", json={"email": email, "password": password})
        login_resp = await bc.post("/auth/login", json={"email": email, "password": password})
        token = login_resp.json()["access_token"]
        org_resp = await bc.post(
            "/organizations",
            json={"name": "Microfinance SaaS", "slug": "mf-saas"},
            headers={"Authorization": f"Bearer {token}"},
        )
        org_id = org_resp.json()["id"]

    async with control_db_session_factory() as db:
        db.add(
            MFPlatformAccount(
                cp_organization_id=org_id,
                cp_email=email,
                encrypted_cp_password=encrypt_secret(password),
            )
        )
        await db.commit()
    return org_id


@pytest_asyncio.fixture
async def active_region(backend_db_session_factory):
    """A Region + ACTIVE Node for the backend to place new databases on — same
    seeding sdk/tests and backend/tests do directly against the DB, since
    creating infra is platform-admin-only and out of scope for these tests."""
    from app.core.timeutil import utcnow
    from app.models.node import Node, NodeStatus
    from app.models.region import Region

    async with backend_db_session_factory() as db:
        region = Region(code="eu-mf", name="Microfinance Test Region")
        db.add(region)
        await db.flush()
        db.add(
            Node(
                region_id=region.id,
                hostname="vps-mf",
                ip_address="203.0.113.77",
                cpu_total=4,
                ram_total_mb=8192,
                storage_total_gb=100,
                node_secret_hash="x",
                status=NodeStatus.ACTIVE,
                last_heartbeat_at=utcnow(),
            )
        )
        await db.commit()
    return "eu-mf"


@pytest_asyncio.fixture
async def onboarded_institution(
    mf_client,
    run_onboarding_job,
    platform_account,
    active_region,
    operator_headers,
    control_db_session_factory,
):
    """Onboards one institution end to end and returns everything a Phase
    9.2+ test needs: the slug, admin auth headers, and a tenant session
    factory for tests that need to inspect the tenant DB directly (e.g. the
    ledger's own unit tests) rather than only through the HTTP API."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from mf_app.db.tenant_session import get_tenant_engine, tenant_database_url
    from mf_app.models.institution import MFInstitution

    resp = await mf_client.post(
        "/institutions",
        json={
            "name": "Test Institution",
            "slug": "test-inst",
            "region_code": active_region,
            "currency": "XOF",
            "admin_email": "admin@test-inst.example",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 201, resp.text
    admin_password = resp.json()["admin_password"]
    assert await run_onboarding_job() is True

    login = await mf_client.post(
        "/institutions/test-inst/auth/login",
        json={"email": "admin@test-inst.example", "password": admin_password},
    )
    assert login.status_code == 200, login.text
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    async with control_db_session_factory() as db:
        institution = (
            await db.execute(select(MFInstitution).where(MFInstitution.slug == "test-inst"))
        ).scalar_one()
        tenant_url = tenant_database_url(institution)

    tenant_session_factory = async_sessionmaker(
        bind=get_tenant_engine(tenant_url), expire_on_commit=False
    )

    return {
        "slug": "test-inst",
        "admin_headers": admin_headers,
        "tenant_session_factory": tenant_session_factory,
    }
