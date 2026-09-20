"""CLI tests invoke the Typer commands directly (via CliRunner) against the same
real, in-process backend as test_client.py — the CLI module builds its own
PlatformClient internally, so these also exercise `_authenticated_client()` and
the slug-resolution helpers, not just the SDK underneath them.
"""

import json

from typer.testing import CliRunner

from eminidatabase_sdk import cli

runner = CliRunner()


def _patch_transport(monkeypatch, transport) -> None:
    """The CLI builds its own PlatformClient from stored credentials, which
    normally talks over real HTTP — point every client it constructs at the
    in-process ASGI transport instead."""
    import eminidatabase_sdk.client as client_module

    original_init = client_module.PlatformClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(client_module.PlatformClient, "__init__", patched_init)


def test_login_and_whoami(monkeypatch, transport):
    _patch_transport(monkeypatch, transport)

    register = runner.invoke(
        cli.app,
        ["login", "--email", "cli1@example.com", "--password", "correct-horse-battery"],
    )
    # First login attempt registers no one — login only works after registration,
    # so this call is expected to fail; the point is exercising the CLI's error path.
    assert register.exit_code != 0

    import asyncio

    from eminidatabase_sdk.client import PlatformClient

    asyncio.run(
        PlatformClient(base_url="http://test/api/v1", transport=transport).register(
            "cli1@example.com", "correct-horse-battery"
        )
    )

    result = runner.invoke(
        cli.app,
        ["login", "--email", "cli1@example.com", "--password", "correct-horse-battery"],
    )
    assert result.exit_code == 0, result.output
    assert "Logged in as cli1@example.com" in result.output

    whoami = runner.invoke(cli.app, ["whoami"])
    assert whoami.exit_code == 0
    assert json.loads(whoami.output)["email"] == "cli1@example.com"


def test_whoami_without_login_fails_clearly(monkeypatch, transport):
    _patch_transport(monkeypatch, transport)
    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code != 0
    assert "Not logged in" in result.output


def test_organizations_and_projects_flow(monkeypatch, transport):
    _patch_transport(monkeypatch, transport)
    _register_and_login(transport, "cli2@example.com")

    create = runner.invoke(cli.app, ["organizations", "create", "ACME", "acme-cli-1"])
    assert create.exit_code == 0, create.output
    org = json.loads(create.output)
    assert org["slug"] == "acme-cli-1"

    listed = runner.invoke(cli.app, ["organizations", "list"])
    assert any(o["slug"] == "acme-cli-1" for o in json.loads(listed.output))

    project = runner.invoke(cli.app, ["projects", "create", "acme-cli-1", "Shop", "shop"])
    assert project.exit_code == 0, project.output
    assert json.loads(project.output)["slug"] == "shop"

    projects = runner.invoke(cli.app, ["projects", "list", "acme-cli-1"])
    assert any(p["slug"] == "shop" for p in json.loads(projects.output))


def test_db_create_list_get_by_slug(monkeypatch, transport, db_session_factory):
    _patch_transport(monkeypatch, transport)
    _register_and_login(transport, "cli3@example.com")
    runner.invoke(cli.app, ["organizations", "create", "ACME", "acme-cli-2"])
    runner.invoke(cli.app, ["projects", "create", "acme-cli-2", "Shop", "shop"])

    _seed_active_node(db_session_factory, "eu-cli")

    import app.worker as worker_module

    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        class _Resp:
            def json(self_inner):
                return {"status": "ok"}

        return _Resp()

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", db_session_factory)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)

    create = runner.invoke(
        cli.app,
        ["db", "create", "acme-cli-2", "shop", "production", "--region", "eu-cli"],
    )
    assert create.exit_code == 0, create.output
    assert json.loads(create.output)["database"]["status"] == "creating"

    import asyncio

    asyncio.run(worker_module.run_once())

    get = runner.invoke(cli.app, ["db", "get", "acme-cli-2", "shop", "production"])
    assert get.exit_code == 0, get.output
    assert json.loads(get.output)["status"] == "running"

    listed = runner.invoke(cli.app, ["db", "list", "acme-cli-2", "shop"])
    assert any(d["name"] == "production" for d in json.loads(listed.output))


def _register_and_login(transport, email: str, password: str = "correct-horse-battery") -> None:
    import asyncio

    from eminidatabase_sdk.client import PlatformClient

    async def go():
        client = PlatformClient(base_url="http://test/api/v1", transport=transport)
        await client.register(email, password)

    asyncio.run(go())
    result = runner.invoke(cli.app, ["login", "--email", email, "--password", password])
    assert result.exit_code == 0, result.output


def _seed_active_node(db_session_factory, region_code: str) -> None:
    import asyncio

    from app.core.timeutil import utcnow
    from app.models.node import Node, NodeStatus
    from app.models.region import Region

    async def go():
        async with db_session_factory() as db:
            region = Region(code=region_code, name="CLI Test Region")
            db.add(region)
            await db.flush()
            db.add(
                Node(
                    region_id=region.id,
                    hostname=f"vps-{region_code}",
                    ip_address="203.0.113.99",
                    cpu_total=4,
                    ram_total_mb=8192,
                    storage_total_gb=100,
                    node_secret_hash="x",
                    status=NodeStatus.ACTIVE,
                    last_heartbeat_at=utcnow(),
                )
            )
            await db.commit()

    asyncio.run(go())
