from httpx import AsyncClient

import app.worker as worker_module
from app.services.agent_client import AgentRequestError
from app.services.sql_editor import SqlExecutionResult
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _FakeAgentResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = "ok"

    def json(self):
        return self._payload


async def _fake_call_agent_factory(payload=None):
    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse(payload if payload is not None else {"status": "ok"})

    return _fake_call_agent


async def _create_running_database(
    client: AsyncClient, monkeypatch, suffix: str
) -> tuple[dict, dict, dict, str]:
    """Returns (owner_headers, org, project, database_id) for a database already
    RUNNING, using the same mocked-agent worker tick pattern as test_databases.py."""

    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"status": "ok"})

    admin_headers = await register_platform_admin(client, f"p4admin{suffix}@example.com")
    owner_headers = await register_and_login(client, f"p4owner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": f"acme-p4-{suffix}"},
            headers=owner_headers,
        )
    ).json()
    project = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/projects",
            json={"name": "Shop", "slug": "shop"},
            headers=owner_headers,
        )
    ).json()
    region = await create_region(client, admin_headers, f"eu-p4-{suffix}")
    await register_and_activate_node(
        client, admin_headers, region["code"], hostname=f"vps-p4-{suffix}"
    )

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)
    await worker_module.run_once()

    return owner_headers, org, project, database_id


def _base_url(org: dict, project: dict, database_id: str) -> str:
    return f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases/{database_id}"


async def test_create_list_delete_role(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "role1"
    )
    base = _base_url(org, project, database_id)

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_roles.call_agent",
        await _fake_call_agent_factory(),
    )

    create_resp = await client.post(
        f"{base}/roles", json={"name": "reporting", "scope": "readonly"}, headers=owner_headers
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["role_name"].startswith("u_")
    assert body["name"] == "reporting"
    role_credential_id = body["id"]

    list_resp = await client.get(f"{base}/roles", headers=owner_headers)
    names = {r["name"] for r in list_resp.json()}
    assert "reporting" in names
    assert None in names  # the original owner credential has no display name
    scopes = {r["scope"] for r in list_resp.json()}
    assert "admin" in scopes or "app" in scopes  # owner credential from Phase 3

    delete_resp = await client.delete(f"{base}/roles/{role_credential_id}", headers=owner_headers)
    assert delete_resp.status_code == 204

    list_after = await client.get(f"{base}/roles", headers=owner_headers)
    assert role_credential_id not in [r["id"] for r in list_after.json()]


async def test_cannot_create_or_delete_admin_scope_role(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "role2"
    )
    base = _base_url(org, project, database_id)
    monkeypatch.setattr(
        "app.api.v1.endpoints.database_roles.call_agent",
        await _fake_call_agent_factory(),
    )

    resp = await client.post(
        f"{base}/roles", json={"name": "attempt", "scope": "admin"}, headers=owner_headers
    )
    assert resp.status_code == 400

    roles = (await client.get(f"{base}/roles", headers=owner_headers)).json()
    owner_credential = next(r for r in roles if r["is_primary"])
    delete_resp = await client.delete(
        f"{base}/roles/{owner_credential['id']}", headers=owner_headers
    )
    assert delete_resp.status_code == 400


async def test_readonly_member_can_list_roles_but_not_create(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "role3"
    )
    base = _base_url(org, project, database_id)
    readonly_headers = await register_and_login(client, "p4readonly3@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "p4readonly3@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    assert (await client.get(f"{base}/roles", headers=readonly_headers)).status_code == 200
    resp = await client.post(
        f"{base}/roles", json={"name": "attempt", "scope": "readonly"}, headers=readonly_headers
    )
    assert resp.status_code == 403


async def test_extensions_install_list_drop(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "ext1"
    )
    base = _base_url(org, project, database_id)

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_ops.call_agent",
        await _fake_call_agent_factory({"status": "installed", "name": "pgcrypto"}),
    )
    install_resp = await client.post(
        f"{base}/extensions", json={"name": "pgcrypto"}, headers=owner_headers
    )
    assert install_resp.status_code == 201

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_ops.call_agent",
        await _fake_call_agent_factory(
            [{"name": "pgcrypto", "installed": True, "version": "1.3"}]
        ),
    )
    list_resp = await client.get(f"{base}/extensions", headers=owner_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["installed"] is True

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_ops.call_agent",
        await _fake_call_agent_factory({"status": "dropped", "name": "pgcrypto"}),
    )
    drop_resp = await client.delete(f"{base}/extensions/pgcrypto", headers=owner_headers)
    assert drop_resp.status_code == 204


async def test_disallowed_extension_surfaces_as_client_error_not_500(
    client: AsyncClient, monkeypatch
):
    """Regression test: a rejection from the agent (e.g. extension not on the
    allowlist) must reach the caller as a 4xx, not get swallowed into a 500 by
    call_agent conflating 'agent said no' with 'agent unreachable'."""
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "ext3"
    )
    base = _base_url(org, project, database_id)

    async def _rejecting_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        raise AgentRequestError(400, "Extension 'plpythonu' is not on the allowed list")

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_ops.call_agent", _rejecting_call_agent
    )
    resp = await client.post(
        f"{base}/extensions", json={"name": "plpythonu"}, headers=owner_headers
    )
    assert resp.status_code == 400
    assert "not on the allowed list" in resp.json()["detail"]


async def test_readonly_cannot_install_extension_but_can_list(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "ext2"
    )
    base = _base_url(org, project, database_id)
    readonly_headers = await register_and_login(client, "p4readonly_ext2@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "p4readonly_ext2@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_ops.call_agent", await _fake_call_agent_factory([])
    )
    assert (await client.get(f"{base}/extensions", headers=readonly_headers)).status_code == 200
    resp = await client.post(
        f"{base}/extensions", json={"name": "pgcrypto"}, headers=readonly_headers
    )
    assert resp.status_code == 403


async def test_metrics_and_tables(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "obs1"
    )
    base = _base_url(org, project, database_id)

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_ops.call_agent",
        await _fake_call_agent_factory(
            {"size_bytes": 8192, "active_connections": 1, "max_connections": 100}
        ),
    )
    metrics_resp = await client.get(f"{base}/metrics", headers=owner_headers)
    assert metrics_resp.status_code == 200
    assert metrics_resp.json()["size_bytes"] == 8192

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_ops.call_agent",
        await _fake_call_agent_factory(
            [{"name": "customers", "columns": [], "indexes": []}]
        ),
    )
    tables_resp = await client.get(f"{base}/tables", headers=owner_headers)
    assert tables_resp.status_code == 200
    assert tables_resp.json()[0]["name"] == "customers"


async def test_sql_execute_records_history(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "sql1"
    )
    base = _base_url(org, project, database_id)

    async def _fake_execute_query(database, credential, query):
        return SqlExecutionResult(
            status="succeeded",
            columns=["id"],
            rows=[[1]],
            row_count=1,
            truncated=False,
            duration_ms=5,
            error=None,
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.database_sql.execute_query", _fake_execute_query
    )

    exec_resp = await client.post(
        f"{base}/sql/execute", json={"query": "SELECT 1 as id"}, headers=owner_headers
    )
    assert exec_resp.status_code == 200
    body = exec_resp.json()
    assert body["status"] == "succeeded"
    assert body["rows"] == [[1]]

    history_resp = await client.get(f"{base}/sql/history", headers=owner_headers)
    assert history_resp.status_code == 200
    assert history_resp.json()[0]["query_text"] == "SELECT 1 as id"


async def test_sql_execute_requires_running_database(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "p4admin_sql2@example.com")
    owner_headers = await register_and_login(client, "p4owner_sql2@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": "acme-p4-sql2"},
            headers=owner_headers,
        )
    ).json()
    project = (
        await client.post(
            f"/api/v1/organizations/{org['id']}/projects",
            json={"name": "Shop", "slug": "shop"},
            headers=owner_headers,
        )
    ).json()
    region = await create_region(client, admin_headers, "eu-p4-sql2")
    # No node registered -> database stays CREATING forever.
    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    resp = await client.post(
        _base_url(org, project, database_id) + "/sql/execute",
        json={"query": "SELECT 1"},
        headers=owner_headers,
    )
    assert resp.status_code == 409


async def test_readonly_cannot_execute_sql_but_can_read_history(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "sql3"
    )
    base = _base_url(org, project, database_id)
    readonly_headers = await register_and_login(client, "p4readonly_sql3@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "p4readonly_sql3@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    resp = await client.post(
        f"{base}/sql/execute", json={"query": "SELECT 1"}, headers=readonly_headers
    )
    assert resp.status_code == 403
    assert (await client.get(f"{base}/sql/history", headers=readonly_headers)).status_code == 200


async def test_saved_queries_crud(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "saved1"
    )
    base = _base_url(org, project, database_id)

    create_resp = await client.post(
        f"{base}/sql/saved-queries",
        json={"name": "Top customers", "query": "SELECT * FROM customers LIMIT 10"},
        headers=owner_headers,
    )
    assert create_resp.status_code == 201
    saved_id = create_resp.json()["id"]

    list_resp = await client.get(f"{base}/sql/saved-queries", headers=owner_headers)
    assert any(q["id"] == saved_id for q in list_resp.json())

    delete_resp = await client.delete(f"{base}/sql/saved-queries/{saved_id}", headers=owner_headers)
    assert delete_resp.status_code == 204

    list_after = await client.get(f"{base}/sql/saved-queries", headers=owner_headers)
    assert all(q["id"] != saved_id for q in list_after.json())


async def test_rotate_role_changes_password(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "rotate1"
    )
    base = _base_url(org, project, database_id)
    monkeypatch.setattr(
        "app.api.v1.endpoints.database_roles.call_agent",
        await _fake_call_agent_factory(),
    )

    create_resp = await client.post(
        f"{base}/roles", json={"name": "svc", "scope": "app"}, headers=owner_headers
    )
    credential_id = create_resp.json()["id"]
    original_password = create_resp.json()["password"]

    rotate_resp = await client.post(f"{base}/roles/{credential_id}/rotate", headers=owner_headers)
    assert rotate_resp.status_code == 200
    assert rotate_resp.json()["password"] != original_password
    assert rotate_resp.json()["role_name"] == create_resp.json()["role_name"]
