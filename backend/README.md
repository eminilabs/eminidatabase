# Control Plane — Backend (Phases 1-8, 10-12 partial)

FastAPI backend for the Cloud Database Platform's Control Plane: auth,
organizations, memberships/RBAC, projects, API keys, audit log (Phase 1); regions,
nodes, an internal CA for mTLS, node registration/heartbeat (Phase 2); the Database
Orchestrator — placement, real PostgreSQL provisioning via the Data Plane Agent,
credentials, lifecycle, a job queue (Phase 3); additional PostgreSQL roles,
extensions, a SQL Editor, schema introspection, and metrics (Phase 4); backups,
restore, and periodic backup verification (Phase 5); replication status, cluster
management, and automatic/manual failover (Phase 6); vertical resize and
cross-node migration (Phase 7); webhooks with signed delivery (Phase 8, consumed
by the official SDK/CLI in [../sdk/](../sdk/README.md)); plans, quotas, real usage
metering, and automatic invoice generation (Phase 10 — the platform billing
itself, unlike Phase 9's microfinance module which is a separate client
deployable, cf. [../microfinance/README.md](../microfinance/README.md)); rate
limiting, MFA-for-paying-plans enforcement, and a real, reported disaster-recovery
test pass (Phase 11 — see
[../docs/architecture/05-backup-ha-scaling.md §5.7](../docs/architecture/05-backup-ha-scaling.md#57-rapport-de-test-des-scénarios-de-disaster-recovery-phase-11-2026-09-19)
for the full report); real NOWPayments (crypto) and FedaPay (mobile money, no
redirect) payment gateways closing the `PaymentProvider` abstraction, plus a
Resend-backed notification system (welcome/invoice/payment/subscription emails)
that didn't exist before (see
[../docs/architecture/08-microfinance-et-billing.md §8.17](../docs/architecture/08-microfinance-et-billing.md#817-passerelles-de-paiement-réelles-et-notifications-2026-09-19--implémentée)).
See
[../docs/architecture/](../docs/architecture/) for the full architecture and
[../docs/architecture/09-plan-de-phases.md](../docs/architecture/09-plan-de-phases.md)
for what comes next.

No frontend work happens against this backend yet — see the backend-first sequencing
decision in that same document. Exercise the API via Swagger UI, the interactive docs,
or curl/httpie.

## Setup

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on Unix
pip install -r requirements.txt
cp .env.example .env       # then fill in DATABASE_URL / JWT_SECRET_KEY
```

`DATABASE_URL` defaults to a local SQLite file if unset, which is fine for quick
manual testing. For anything resembling real development, point it at a Postgres
instance (Neon works well) per Règle 19 — this database holds Control Plane
**metadata only**, never customer databases.

## Run

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

## Run the orchestrator worker

Database create/delete/suspend/resume are asynchronous — the API enqueues a `Job`
row and returns immediately (202); a separate process executes it:

```bash
python -m app.worker
```

Nothing gets provisioned without this running. It polls the `jobs` table (see
`app/services/jobs.py` for why that's the queue instead of Redis/Arq at this stage)
and calls the relevant Data Plane Agent over mTLS for each job — see
`../agent/README.md` to run one, and
`../docs/architecture/09-plan-de-phases.md` (Phase 3) for how this was verified
end-to-end against a real PostgreSQL instance. The same worker also delivers
webhooks (`deliver_webhook` jobs, Phase 8) — a database/backup lifecycle event
calls `app/services/webhook_orchestrator.py`'s `emit_event()`, which enqueues one
signed HTTP delivery per subscribed, active webhook.

## Run the backup scheduler

Separate again from both the API and the worker — decides *when* to back up or
verify, the worker executes the actual job once enqueued:

```bash
python -m app.scheduler
```

Ticks every 60s: enqueues an automatic backup for any `RUNNING` database whose
`backup_policy` (`PUT .../databases/{id}/backup-policy`) is due, schedules
re-verification of backups older than 7 days since their last check, purges
automatic (never manual) backups past their retention window, and — Phase 6 — checks
every `primary_replica` cluster's primary node; if it looks unhealthy
(`app/services/node_health.py`'s same staleness rule used for placement), it
automatically promotes the best replica via `app/services/ha_orchestrator.py`.
Phase 10 added two more ticks here rather than a new process: `meter_usage()`
calls every `RUNNING` database's real `/metrics` agent endpoint and writes
`UsageRecord` rows (cf. `app/services/billing.py`'s docstring for exactly what's
real vs. an honestly-documented simplification), and `generate_due_invoices()`
turns those into a real `Invoice` once a `Subscription`'s billing period ends.

## High availability: setting up a real streaming replica

`POST /clusters/{id}/replicas` only *adopts* an already-streaming standby into
cluster tracking — cf. `app/services/ha_orchestrator.py`'s docstring for why initial
replica provisioning (`pg_basebackup`) is treated as a one-time infrastructure
bootstrap step, not something the running platform does to itself. See
`../agent/README.md` for how to bootstrap one in this sandbox (Docker containers +
`pg_basebackup -R`), and `docs/architecture/09-plan-de-phases.md` (Phase 6) for how
this was verified end-to-end, including a real `pg_promote()` failover.

## Test

```bash
pytest
ruff check app tests
```

Tests run against an in-memory SQLite database (see `tests/conftest.py`) — no external
database required.

## Migrations

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

The custom `GUID` column type (`app/db/types.py`) needs `render_item` support in
`alembic/env.py` to auto-generate its import — already configured, don't remove it.

## Layout

```
app/
  core/       settings, password hashing, JWT, TOTP/MFA, RBAC dependency wiring
  db/         SQLAlchemy base, async session, portable GUID type
  models/     SQLAlchemy ORM models (Phase 1 subset of docs/architecture/02-modele-donnees.md)
  schemas/    Pydantic request/response models
  services/   audit logging, RBAC permission matrix
  api/v1/     versioned routers and endpoints
tests/        pytest + httpx async tests, one file per resource
alembic/      migrations
```
