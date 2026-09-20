# Python SDK & CLI (Phase 8)

Official Python SDK (`eminidatabase_sdk.client.PlatformClient`) and CLI (`platform`)
for the Cloud Database Platform. Every CLI command is a thin wrapper over the SDK,
and every SDK method is a thin wrapper over one API call — no client-side business
logic, no caching, no retries; that all lives in the platform itself (see the
backend's job/retry machinery). This is what proves the exit criterion of
[../docs/architecture/09-plan-de-phases.md](../docs/architecture/09-plan-de-phases.md)
(Phase 8): an external developer can create and manage a database entirely through
the CLI, without ever touching a dashboard (which doesn't exist yet — see the
backend-first sequencing rule in that same document).

TypeScript/Go SDKs are deliberately **not** in this package — see the Phase 8 note
in the plan of phases for why they're deferred to Phase F (built once there's an
actual frontend consuming and exercising them).

## Setup

```bash
cd sdk
python -m venv .venv
./.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on Unix
pip install -e .
pip install -r requirements.txt   # adds pytest/ruff for development
```

The backend must be running (see [../backend/README.md](../backend/README.md)) —
this package is a client, it has no server of its own.

## CLI usage

```bash
platform login --email dev@example.com --password ...
platform whoami

platform organizations create "ACME" acme
platform organizations list

platform projects create acme "Shop" shop
platform projects list acme

platform db create acme shop production --region eu-west-1 --wait
platform db list acme shop
platform db get acme shop production
platform db connect acme shop production
platform db sql acme shop production "SELECT 1"
platform db resize acme shop production --cpu 2 --ram 2048 --storage 20
platform db suspend acme shop production
platform db resume acme shop production
platform db delete acme shop production

platform db backup create acme shop production --wait
platform db backup list acme shop production
platform db restore acme shop production <backup-id> production-restored --wait

platform webhooks create acme https://example.com/hook database.created backup.completed
platform webhooks list acme
platform webhooks deliveries acme <webhook-id>
platform webhooks delete acme <webhook-id>

platform jobs get <job-id>
```

Organization/project/database arguments accept either a slug/name or a UUID —
`_resolve_organization`/`_resolve_project`/`_resolve_database` in `cli.py` do the
lookup, so a developer never has to handle a raw UUID by hand.

Credentials are stored locally in `~/.eminidatabase/credentials.json` (override the
directory with `EMINIDATABASE_CONFIG_DIR`, override the API URL per-command with
`--api-url` or `EMINIDATABASE_API_URL`).

## SDK usage

```python
import asyncio
from eminidatabase_sdk import PlatformClient

async def main():
    client = PlatformClient(base_url="http://127.0.0.1:8000/api/v1")
    await client.login("dev@example.com", "correct-horse-battery")
    org = await client.create_organization("ACME", "acme")
    project = await client.create_project(org["id"], "Shop", "shop")
    result = await client.create_database(org["id"], project["id"], "production", "eu-west-1")
    await client.wait_for_job(result["job_id"])

asyncio.run(main())
```

## Webhooks

`create_webhook` returns the signing secret exactly once, like an API key —
`list_webhooks` never returns it again. Every delivery is a real signed HTTP POST
(same `jobs`/worker infrastructure as everything else in the backend, cf.
`app/services/webhook_orchestrator.py`):

- `X-Eminidatabase-Event`: the event type (e.g. `database.created`)
- `X-Eminidatabase-Signature`: `sha256=<hmac-sha256 of the exact request body, hex>`

Verify it the same way the platform computes it:

```python
import hashlib, hmac

expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, received_signature.removeprefix("sha256="))
```

## Test

```bash
pytest
ruff check .
```

Tests run against the real backend FastAPI app in-process (`httpx.ASGITransport`,
see `tests/conftest.py`) — no live server needed, but every request goes through
real routing/validation/DB, the same pattern `backend/tests/conftest.py` itself
uses. `db_session_factory` is exposed as a fixture rather than imported as a bare
module (`from tests.conftest import ...`) deliberately: both `sdk/tests/` and
`backend/tests/` resolve as a package named `tests` once the backend is added to
`sys.path`, and a bare import silently picked up the wrong one, corrupting the
shared FastAPI `dependency_overrides` dict for the rest of the test session — see
the Phase 8 entry in
[../docs/architecture/09-plan-de-phases.md](../docs/architecture/09-plan-de-phases.md)
for the full story.

## Layout

```
eminidatabase_sdk/
  client.py      PlatformClient — one method per API call
  cli.py         Typer app (`platform`), built entirely on top of PlatformClient
  auth_store.py  local credential persistence (~/.eminidatabase/credentials.json)
  exceptions.py  ApiError
tests/           pytest + httpx ASGI transport, one file for the SDK, one for the CLI
```
