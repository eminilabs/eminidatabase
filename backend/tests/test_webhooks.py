import hashlib
import hmac

from httpx import AsyncClient

import app.worker as worker_module
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _FakeAgentResponse:
    def __init__(self, payload=None):
        self._payload = payload if payload is not None else {"status": "ok"}

    def json(self):
        return self._payload


async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
    return _FakeAgentResponse()


class _FakeWebhookResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text
        self.is_success = 200 <= status_code < 300


class _FakeHttpxClient:
    """Stands in for httpx.AsyncClient — records each POST for assertions and
    returns a canned response instead of hitting a real network endpoint."""

    received: list[dict] = []
    response_status_code = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, content=None, headers=None):
        type(self).received.append({"url": url, "content": content, "headers": headers})
        return _FakeWebhookResponse(status_code=type(self).response_status_code)


async def _create_org_project(client: AsyncClient, suffix: str) -> tuple[dict, dict, dict]:
    owner_headers = await register_and_login(client, f"p8owner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": f"acme-p8-{suffix}"},
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
    return owner_headers, org, project


async def test_create_webhook_requires_https(client: AsyncClient):
    owner_headers, org, _ = await _create_org_project(client, "wh1")
    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/webhooks",
        json={"url": "http://example.com/hook", "event_types": ["database.created"]},
        headers=owner_headers,
    )
    assert resp.status_code == 422


async def test_create_webhook_rejects_unknown_event_type(client: AsyncClient):
    owner_headers, org, _ = await _create_org_project(client, "wh2")
    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["database.exploded"]},
        headers=owner_headers,
    )
    assert resp.status_code == 422


async def test_create_list_delete_webhook(client: AsyncClient):
    owner_headers, org, _ = await _create_org_project(client, "wh3")
    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["database.created"]},
        headers=owner_headers,
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["secret"]
    webhook_id = body["id"]

    list_resp = await client.get(
        f"/api/v1/organizations/{org['id']}/webhooks", headers=owner_headers
    )
    assert len(list_resp.json()) == 1
    assert "secret" not in list_resp.json()[0]

    delete_resp = await client.delete(
        f"/api/v1/organizations/{org['id']}/webhooks/{webhook_id}", headers=owner_headers
    )
    assert delete_resp.status_code == 204
    assert (
        await client.get(f"/api/v1/organizations/{org['id']}/webhooks", headers=owner_headers)
    ).json() == []


async def test_readonly_cannot_manage_webhooks(client: AsyncClient):
    owner_headers, org, _ = await _create_org_project(client, "wh4")
    readonly_headers = await register_and_login(client, "p8readonly4@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "p8readonly4@example.com", "role": "readonly"},
        headers=owner_headers,
    )
    resp = await client.post(
        f"/api/v1/organizations/{org['id']}/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["database.created"]},
        headers=readonly_headers,
    )
    assert resp.status_code == 403


async def test_webhook_delivered_on_database_created(client: AsyncClient, monkeypatch):
    admin_headers = await register_platform_admin(client, "p8admin5@example.com")
    owner_headers, org, project = await _create_org_project(client, "wh5")
    region = await create_region(client, admin_headers, "eu-p8-wh5")
    await register_and_activate_node(client, admin_headers, region["code"], hostname="vps-p8-wh5")

    webhook_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["database.created"]},
        headers=owner_headers,
    )
    webhook_id = webhook_resp.json()["id"]
    secret = webhook_resp.json()["secret"]

    _FakeHttpxClient.received = []
    _FakeHttpxClient.response_status_code = 200
    monkeypatch.setattr("app.services.webhook_orchestrator.httpx.AsyncClient", _FakeHttpxClient)
    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)

    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    assert create_resp.status_code == 202

    await worker_module.run_once()  # create_database succeeds -> enqueues delivery
    await worker_module.run_once()  # deliver_webhook

    assert len(_FakeHttpxClient.received) == 1
    call = _FakeHttpxClient.received[0]
    assert call["url"] == "https://example.com/hook"
    assert call["headers"]["X-Eminidatabase-Event"] == "database.created"
    expected_signature = hmac.new(secret.encode(), call["content"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-Eminidatabase-Signature"] == f"sha256={expected_signature}"

    deliveries = await client.get(
        f"/api/v1/organizations/{org['id']}/webhooks/{webhook_id}/deliveries",
        headers=owner_headers,
    )
    assert deliveries.json()[0]["status"] == "succeeded"
    assert deliveries.json()[0]["response_code"] == 200


async def test_webhook_not_triggered_for_unsubscribed_event(client: AsyncClient, monkeypatch):
    admin_headers = await register_platform_admin(client, "p8admin6@example.com")
    owner_headers, org, project = await _create_org_project(client, "wh6")
    region = await create_region(client, admin_headers, "eu-p8-wh6")
    await register_and_activate_node(client, admin_headers, region["code"], hostname="vps-p8-wh6")

    await client.post(
        f"/api/v1/organizations/{org['id']}/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["backup.completed"]},
        headers=owner_headers,
    )

    _FakeHttpxClient.received = []
    monkeypatch.setattr("app.services.webhook_orchestrator.httpx.AsyncClient", _FakeHttpxClient)
    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)

    await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    await worker_module.run_once()  # create_database only — no matching subscription

    assert _FakeHttpxClient.received == []


async def test_webhook_delivery_retries_then_fails_terminally(client: AsyncClient, monkeypatch):
    admin_headers = await register_platform_admin(client, "p8admin7@example.com")
    owner_headers, org, project = await _create_org_project(client, "wh7")
    region = await create_region(client, admin_headers, "eu-p8-wh7")
    await register_and_activate_node(client, admin_headers, region["code"], hostname="vps-p8-wh7")

    webhook_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["database.created"]},
        headers=owner_headers,
    )
    webhook_id = webhook_resp.json()["id"]

    _FakeHttpxClient.received = []
    _FakeHttpxClient.response_status_code = 500
    monkeypatch.setattr("app.services.webhook_orchestrator.httpx.AsyncClient", _FakeHttpxClient)
    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.orchestrator.call_agent", _fake_call_agent)

    await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    await worker_module.run_once()  # create_database

    async with TestSessionLocal() as db:
        from sqlalchemy import select

        from app.models.job import Job

        job = (await db.execute(select(Job).where(Job.type == "deliver_webhook"))).scalar_one()
        job.max_attempts = 1
        await db.commit()

    await worker_module.run_once()  # deliver_webhook — fails terminally

    deliveries = await client.get(
        f"/api/v1/organizations/{org['id']}/webhooks/{webhook_id}/deliveries",
        headers=owner_headers,
    )
    assert deliveries.json()[0]["status"] == "failed"
