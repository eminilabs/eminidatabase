import datetime as dt
import uuid

from httpx import AsyncClient
from sqlalchemy import select

import app.scheduler as scheduler_module
import app.worker as worker_module
from app.models.backup import Backup, BackupStatus, BackupType
from app.models.job import Job
from tests.conftest import TestSessionLocal, register_and_login, register_platform_admin
from tests.factories import create_region, register_and_activate_node


class _FakeAgentResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


async def _create_running_database(
    client: AsyncClient, monkeypatch, suffix: str
) -> tuple[dict, dict, dict, str]:
    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"status": "ok"})

    admin_headers = await register_platform_admin(client, f"p5admin{suffix}@example.com")
    owner_headers = await register_and_login(client, f"p5owner{suffix}@example.com")
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": "ACME", "slug": f"acme-p5-{suffix}"},
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
    region = await create_region(client, admin_headers, f"eu-p5-{suffix}")
    await register_and_activate_node(
        client, admin_headers, region["code"], hostname=f"vps-p5-{suffix}"
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


async def test_manual_backup_completes(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk1"
    )
    base = _base_url(org, project, database_id)

    create_resp = await client.post(f"{base}/backups", headers=owner_headers)
    assert create_resp.status_code == 202
    body = create_resp.json()
    assert body["backup"]["status"] == "pending"
    backup_id = body["backup"]["id"]
    job_id = body["job_id"]

    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"status": "completed", "storage_key": "x", "size_bytes": 4096})

    monkeypatch.setattr("app.services.backup_orchestrator.call_agent", _fake_call_agent)
    await worker_module.run_once()

    job_resp = await client.get(f"/api/v1/jobs/{job_id}", headers=owner_headers)
    assert job_resp.json()["status"] == "succeeded"

    backup_resp = await client.get(f"{base}/backups/{backup_id}", headers=owner_headers)
    assert backup_resp.json()["status"] == "completed"
    assert backup_resp.json()["size_bytes"] == 4096

    list_resp = await client.get(f"{base}/backups", headers=owner_headers)
    assert any(b["id"] == backup_id for b in list_resp.json())


async def test_backup_requires_running_database(client: AsyncClient):
    admin_headers = await register_platform_admin(client, "p5admin2@example.com")
    owner_headers = await register_and_login(client, "p5owner2@example.com")
    org = (
        await client.post(
            "/api/v1/organizations", json={"name": "ACME", "slug": "acme-p5-2"},
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
    region = await create_region(client, admin_headers, "eu-p5-2")
    # No node registered -> database never leaves CREATING.
    create_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/projects/{project['id']}/databases",
        json={"name": "production", "region_code": region["code"]},
        headers=owner_headers,
    )
    database_id = create_resp.json()["database"]["id"]

    resp = await client.post(
        _base_url(org, project, database_id) + "/backups", headers=owner_headers
    )
    assert resp.status_code == 409


async def test_readonly_cannot_create_backup_but_can_list(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk3"
    )
    base = _base_url(org, project, database_id)
    readonly_headers = await register_and_login(client, "p5readonly3@example.com")
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "p5readonly3@example.com", "role": "readonly"},
        headers=owner_headers,
    )

    assert (await client.post(f"{base}/backups", headers=readonly_headers)).status_code == 403
    assert (await client.get(f"{base}/backups", headers=readonly_headers)).status_code == 200


async def test_restore_creates_new_running_database(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk4"
    )
    base = _base_url(org, project, database_id)

    create_resp = await client.post(f"{base}/backups", headers=owner_headers)
    backup_id = create_resp.json()["backup"]["id"]

    async def _fake_backup_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"status": "completed", "storage_key": "x", "size_bytes": 100})

    monkeypatch.setattr(
        "app.services.backup_orchestrator.call_agent", _fake_backup_call_agent
    )
    await worker_module.run_once()  # completes the backup

    restore_resp = await client.post(
        f"{base}/backups/{backup_id}/restore",
        json={"name": "production-restored"},
        headers=owner_headers,
    )
    assert restore_resp.status_code == 202
    restored = restore_resp.json()["database"]
    assert restored["status"] == "restoring"
    assert restored["id"] != database_id

    await worker_module.run_once()  # executes the restore job

    check_resp = await client.get(_base_url(org, project, restored["id"]), headers=owner_headers)
    assert check_resp.json()["status"] == "running"
    assert check_resp.json()["connection_host"] is not None


async def test_restore_rejects_non_restorable_backup(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk5"
    )
    base = _base_url(org, project, database_id)

    create_resp = await client.post(f"{base}/backups", headers=owner_headers)
    backup_id = create_resp.json()["backup"]["id"]
    # Deliberately not running the worker — backup stays PENDING.

    resp = await client.post(
        f"{base}/backups/{backup_id}/restore",
        json={"name": "too-early"},
        headers=owner_headers,
    )
    assert resp.status_code == 409


async def test_verify_backup_marks_verified(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk6"
    )
    base = _base_url(org, project, database_id)

    create_resp = await client.post(f"{base}/backups", headers=owner_headers)
    backup_id = create_resp.json()["backup"]["id"]

    async def _fake_backup_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"status": "completed", "storage_key": "x", "size_bytes": 100})

    monkeypatch.setattr(
        "app.services.backup_orchestrator.call_agent", _fake_backup_call_agent
    )
    await worker_module.run_once()  # complete the backup

    async with TestSessionLocal() as db:
        from app.services.jobs import enqueue

        await enqueue(
            db,
            type="verify_backup",
            payload={"backup_id": backup_id},
            resource_type="backup",
            resource_id=uuid.UUID(backup_id),
        )
        await db.commit()

    async def _fake_verify_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"verified": True, "detail": "Restored successfully; 1 table"})

    monkeypatch.setattr(
        "app.services.backup_orchestrator.call_agent", _fake_verify_call_agent
    )
    await worker_module.run_once()

    backup_resp = await client.get(f"{base}/backups/{backup_id}", headers=owner_headers)
    assert backup_resp.json()["status"] == "verified"
    assert backup_resp.json()["verified_at"] is not None


async def test_backup_job_terminal_failure_marks_backup_failed(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk7"
    )
    base = _base_url(org, project, database_id)

    create_resp = await client.post(f"{base}/backups", headers=owner_headers)
    backup_id = create_resp.json()["backup"]["id"]

    async def _always_fails(node, method, path, *, json=None, params=None, timeout=30.0):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr("app.services.backup_orchestrator.call_agent", _always_fails)

    async with TestSessionLocal() as db:
        job = (
            await db.execute(select(Job).where(Job.resource_id == uuid.UUID(backup_id)))
        ).scalar_one()
        job.max_attempts = 1
        await db.commit()

    await worker_module.run_once()

    backup_resp = await client.get(f"{base}/backups/{backup_id}", headers=owner_headers)
    assert backup_resp.json()["status"] == "failed"


async def test_backup_policy_get_and_set(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk8"
    )
    base = _base_url(org, project, database_id)

    default_policy = await client.get(f"{base}/backup-policy", headers=owner_headers)
    assert default_policy.json()["enabled"] is False

    set_resp = await client.put(
        f"{base}/backup-policy",
        json={"enabled": True, "frequency_hours": 12, "retention_days": 30},
        headers=owner_headers,
    )
    assert set_resp.status_code == 200

    get_resp = await client.get(f"{base}/backup-policy", headers=owner_headers)
    assert get_resp.json() == {"enabled": True, "frequency_hours": 12, "retention_days": 30}


async def test_scheduler_enqueues_backup_when_due(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk9"
    )
    base = _base_url(org, project, database_id)
    await client.put(
        f"{base}/backup-policy",
        json={"enabled": True, "frequency_hours": 1, "retention_days": 7},
        headers=owner_headers,
    )

    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", TestSessionLocal)
    enqueued = await scheduler_module.enqueue_due_backups()
    assert enqueued == 1

    backups = (await client.get(f"{base}/backups", headers=owner_headers)).json()
    assert any(b["type"] == "automatic" for b in backups)

    # A second tick immediately after must not double-schedule.
    enqueued_again = await scheduler_module.enqueue_due_backups()
    assert enqueued_again == 0


async def test_scheduler_purges_only_expired_automatic_backups(client: AsyncClient, monkeypatch):
    owner_headers, org, project, database_id = await _create_running_database(
        client, monkeypatch, "bk10"
    )
    base = _base_url(org, project, database_id)
    await client.put(
        f"{base}/backup-policy",
        json={"enabled": True, "frequency_hours": 24, "retention_days": 1},
        headers=owner_headers,
    )

    old_time = dt.datetime.now(dt.UTC) - dt.timedelta(days=5)
    async with TestSessionLocal() as db:
        auto_backup = Backup(
            database_id=uuid.UUID(database_id),
            type=BackupType.AUTOMATIC,
            status=BackupStatus.COMPLETED,
            storage_key="backups/old-auto.dump.enc",
            created_at=old_time,
        )
        manual_backup = Backup(
            database_id=uuid.UUID(database_id),
            type=BackupType.MANUAL,
            status=BackupStatus.COMPLETED,
            storage_key="backups/old-manual.dump.enc",
            created_at=old_time,
        )
        db.add_all([auto_backup, manual_backup])
        await db.commit()
        auto_id, manual_id = auto_backup.id, manual_backup.id

    # This database was never placed on a node (cluster_id is None in this test's
    # DB setup path isn't true here — it IS placed — so purge would try to call the
    # agent; mock it to a no-op success to isolate the retention logic itself.
    async def _fake_call_agent(node, method, path, *, json=None, params=None, timeout=30.0):
        return _FakeAgentResponse({"status": "deleted"})

    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(scheduler_module, "call_agent", _fake_call_agent)

    purged = await scheduler_module.purge_expired_automatic_backups()
    assert purged == 1

    async with TestSessionLocal() as db:
        auto_after = await db.get(Backup, auto_id)
        manual_after = await db.get(Backup, manual_id)
    assert auto_after.status == BackupStatus.PURGED
    assert manual_after.status == BackupStatus.COMPLETED  # untouched
