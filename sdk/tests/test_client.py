import pytest
from httpx import ASGITransport

from eminidatabase_sdk import ApiError, PlatformClient


@pytest.fixture
def client(transport: ASGITransport) -> PlatformClient:
    return PlatformClient(base_url="http://test/api/v1", transport=transport)


async def test_register_login_me(client: PlatformClient):
    await client.register("dev@example.com", "correct-horse-battery")
    token = await client.login("dev@example.com", "correct-horse-battery")
    assert token
    assert client.token == token

    me = await client.me()
    assert me["email"] == "dev@example.com"


async def test_wrong_password_raises_api_error(client: PlatformClient):
    await client.register("dev2@example.com", "correct-horse-battery")
    with pytest.raises(ApiError) as exc_info:
        await client.login("dev2@example.com", "wrong-password")
    assert exc_info.value.status_code == 401


async def test_organization_and_project_lifecycle(client: PlatformClient):
    await client.register("dev3@example.com", "correct-horse-battery")
    await client.login("dev3@example.com", "correct-horse-battery")

    org = await client.create_organization("ACME", "acme-sdk-1")
    assert org["role"] == "owner"

    orgs = await client.list_organizations()
    assert any(o["id"] == org["id"] for o in orgs)

    project = await client.create_project(org["id"], "Shop", "shop")
    projects = await client.list_projects(org["id"])
    assert any(p["id"] == project["id"] for p in projects)
    assert (await client.get_project(org["id"], project["id"]))["id"] == project["id"]


async def test_database_lifecycle_end_to_end(
    client: PlatformClient, monkeypatch, db_session_factory
):
    """Exercises create -> (worker tick) -> get -> resize -> suspend -> resume ->
    delete entirely through the SDK, against the real API (backend importable via
    the sys.path insert in conftest.py)."""
    import app.worker as worker_module
    from app.core.timeutil import utcnow
    from app.models.node import Node, NodeStatus
    from app.models.region import Region

    await client.register("dev4@example.com", "correct-horse-battery")
    await client.login("dev4@example.com", "correct-horse-battery")
    org = await client.create_organization("ACME", "acme-sdk-2")
    project = await client.create_project(org["id"], "Shop", "shop")

    # Platform-admin infra setup (region + active node) done directly against the
    # same in-memory DB the SDK's requests hit — there's no SDK method for this,
    # since it's infra provisioning, not something a tenant developer calls.
    async with db_session_factory() as db:
        region = Region(code="eu-sdk", name="SDK Test Region")
        db.add(region)
        await db.flush()
        node = Node(
            region_id=region.id,
            hostname="vps-sdk",
            ip_address="203.0.113.90",
            cpu_total=4,
            ram_total_mb=8192,
            storage_total_gb=100,
            node_secret_hash="x",
            status=NodeStatus.ACTIVE,
            last_heartbeat_at=utcnow(),
        )
        db.add(node)
        await db.commit()

    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        class _Resp:
            def json(self_inner):
                return {"status": "ok"}

        return _Resp()

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", db_session_factory)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)
    # resize is synchronous (calls the agent directly from the endpoint, not via a
    # job — cf. backend/app/api/v1/endpoints/databases.py), so it needs its own
    # patch target, same as backend/tests/test_scaling.py does.
    monkeypatch.setattr("app.api.v1.endpoints.databases.call_agent", _fake_call_agent)

    result = await client.create_database(org["id"], project["id"], "production", "eu-sdk")
    assert result["database"]["status"] == "creating"

    await worker_module.run_once()

    database = await client.get_database(org["id"], project["id"], result["database"]["id"])
    assert database["status"] == "running"

    resized = await client.resize_database(
        org["id"], project["id"], database["id"],
        cpu_limit=2, ram_limit_mb=2048, storage_limit_gb=20,
    )
    assert resized["cpu_limit"] == 2

    suspended = await client.suspend_database(org["id"], project["id"], database["id"])
    assert suspended["database"]["status"] == "suspending"
    await worker_module.run_once()

    resumed = await client.resume_database(org["id"], project["id"], database["id"])
    assert resumed["database"]["status"] == "updating"
    await worker_module.run_once()

    deleted = await client.delete_database(org["id"], project["id"], database["id"])
    assert deleted["database"]["status"] == "deleting"
    await worker_module.run_once()


async def test_webhook_lifecycle(client: PlatformClient):
    await client.register("dev6@example.com", "correct-horse-battery")
    await client.login("dev6@example.com", "correct-horse-battery")
    org = await client.create_organization("ACME", "acme-sdk-3")

    created = await client.create_webhook(
        org["id"], "https://example.com/hook", ["database.created"]
    )
    assert created["secret"]

    webhooks = await client.list_webhooks(org["id"])
    assert any(w["id"] == created["id"] for w in webhooks)

    deliveries = await client.list_webhook_deliveries(org["id"], created["id"])
    assert deliveries == []

    await client.delete_webhook(org["id"], created["id"])
    assert await client.list_webhooks(org["id"]) == []


async def test_job_and_error_helpers(client: PlatformClient):
    await client.register("dev5@example.com", "correct-horse-battery")
    await client.login("dev5@example.com", "correct-horse-battery")
    with pytest.raises(ApiError) as exc_info:
        await client.get_job("00000000-0000-0000-0000-000000000000")
    assert exc_info.value.status_code == 404
