"""Runs the SDK against the real backend FastAPI app in-process (ASGITransport) —
no live server needed, but every request goes through real routing, real Pydantic
validation, and a real (in-memory) database, exactly like backend/tests/conftest.py
does for the backend's own suite. This is what lets these tests catch a genuinely
broken SDK method (wrong path, wrong payload shape) rather than just testing
against a hand-rolled mock of the API.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app as backend_app  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite://"

test_engine = create_async_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


backend_app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=backend_app)


@pytest.fixture
def db_session_factory():
    """The same session factory `_override_get_db` uses. Exposed as a fixture
    (rather than a plain module import) so a test that needs direct DB access
    can't accidentally import backend/tests/conftest.py instead — both packages
    are named `tests`, and `from tests.conftest import ...` is ambiguous once
    BACKEND_DIR is on sys.path. Importing backend's own conftest re-points
    `dependency_overrides[get_db]` at a second, never-migrated engine, and every
    request silently starts hitting a database with no tables."""
    return TestSessionLocal


@pytest.fixture(autouse=True)
def isolated_cli_config(tmp_path, monkeypatch):
    """Every CLI test gets its own throwaway credentials directory instead of a
    real developer's ~/.eminidatabase."""
    monkeypatch.setenv("EMINIDATABASE_CONFIG_DIR", str(tmp_path / "eminidatabase-config"))
    os.environ.pop("EMINIDATABASE_API_URL", None)
