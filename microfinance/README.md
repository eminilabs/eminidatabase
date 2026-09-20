# Microfinance (Phase 9 — complète)

A microfinance business application built **on top of** the eminidatabase Cloud
Database Platform — not a component of the platform itself. This service is a
*client* of the Control Plane, exactly like any third-party developer using the
Phase 8 SDK: it dogfoods `eminidatabase_sdk.PlatformClient` to provision one
project + database per institution it serves, dynamically, at onboarding time.
See [../docs/architecture/08-microfinance-et-billing.md](../docs/architecture/08-microfinance-et-billing.md)
for the full architecture (§8.3 for why this is a separate deployable, §8.4 for
the two-level Control DB/tenant DB split, §8.10 for the Phase 9 sub-phase plan,
§8.13-§8.15 for what each sub-phase actually built).

- **9.1 Fondations** — institution onboarding, staff auth/RBAC, the tenant
  Alembic migration pipeline.
- **9.2 Ledger et épargne** — the double-entry ledger engine, customers/KYC,
  savings products/accounts, deposit/withdraw.
- **9.3 Crédit** — loan products, the full loan lifecycle (demande →
  approbation → décaissement → remboursement → clôture), deterministic
  repayment schedules. This is the explicit exit criterion of Phase 9.
- **9.4 Comptabilité et paiements** — trial balance / loan portfolio reports,
  a payment provider abstraction (real mobile money integration deferred).

The package is named `mf_app`, not `app` — deliberately, so it can be imported in
the same Python process as `backend/`'s own `app` package during tests (see
Test section below) without a name collision.

## Two databases, two Alembic setups

- **Control DB** (`mf_app/db/control_*.py`, `alembic_control/`) — this
  service's own metadata: `MFPlatformAccount` (its single Control Plane
  identity), `MFInstitution` (slug ↔ project/database mapping + encrypted
  connection), `MFStaffUser` (institution staff logins), `MFJob` (its own
  job queue, same table-is-the-queue pattern as the backend's).
- **Tenant schema** (`mf_app/models/tenant/`, `alembic_tenant/`) — the actual
  business schema: `Branch`/`Agent` (9.1), `Customer`, `InternalAccount`,
  `SavingsProduct`/`SavingsAccount`, `Transaction`/`LedgerEntry` (9.2),
  `LoanProduct`/`Loan`/`RepaymentSchedule`/`RepaymentScheduleLine` (9.3).
  Applied to **every institution's own database**, never to the Control DB.
  `mf_app/services/tenant_migrate.py` runs `alembic -c alembic_tenant.ini
  -x tenant_url=<url> upgrade head` as a subprocess (not in-process — alembic's
  async `env.py` calls `asyncio.run()` internally, which can't nest inside this
  service's already-running event loop) once per institution, at onboarding
  time, and again whenever a new migration ships.

## The ledger — the one rule that matters

Every financial movement (deposit, withdrawal, loan disbursement, loan
repayment) goes through `mf_app/services/ledger.py::post_transaction` — nothing
else ever writes a `LedgerEntry` or mutates a balance column directly. Each
account type declares a "normal balance side" (asset accounts like the
institution's `cash` are normal-debit; a customer's `SavingsAccount` and a
`Loan`'s `outstanding_principal` are normal-credit/debit respectively); the
engine uses that to keep every balance correct regardless of which two account
types a given transaction touches. `GET .../reports/trial-balance` (Phase 9.4)
is the audit proof: it must always report `balanced: true`, since every
transaction the engine ever posts is balanced by construction.

## Setup

```bash
cd microfinance
python -m venv .venv
./.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on Unix
pip install -r requirements.txt
pip install -e ../sdk       # eminidatabase_sdk, Phase 8 — this service's platform client
cp .env.example .env
python -m scripts.generate_operator_token   # put the printed HASH in MF_OPERATOR_TOKEN_HASH
alembic -c alembic_control.ini upgrade head
```

The backend (and its worker) must already be running — see
[../backend/README.md](../backend/README.md).

## Bootstrap this service's own Control Plane identity

One-time, before onboarding any institution:

```bash
python -m scripts.bootstrap_platform_account <email> <password> "<org name>" <org-slug>
```

Registers a CP user, logs in, creates one CP organization, and stores the result
in `MFPlatformAccount` — every institution this service ever onboards becomes a
project inside that one organization (cf. docs/architecture/08 §8.3 for why this
is project-level, not organization-per-institution).

## Run

```bash
uvicorn mf_app.main:app --reload --port 8100
python -m mf_app.worker
```

Swagger UI: http://127.0.0.1:8100/docs

Onboarding a new institution is asynchronous — `POST /institutions` enqueues an
`onboard_institution` job and returns immediately with an `admin_email`/
`admin_password` shown exactly once (like an API key). Nothing gets provisioned
without `mf_app.worker` running.

```bash
curl -X POST http://127.0.0.1:8100/api/v1/institutions \
  -H "Authorization: Bearer <operator token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Coopérative X", "slug": "coop-x", "region_code": "eu-west-1", "currency": "XOF", "admin_email": "admin@coop-x.example"}'
```

Staff then log in at `POST /institutions/{slug}/auth/login`, and the whole
business surface becomes available under `/institutions/{slug}/...`:
`branches`, `staff`, `customers` (+ `PATCH .../kyc`), `savings-products`,
`customers/{id}/savings-accounts` (open), `savings-accounts/{id}/{deposit,
withdraw,transactions}`, `loan-products`, `loans` (+ `{id}/{submit,approve,
reject,disburse,repay,schedule}`), `reports/{trial-balance,loan-portfolio}`.

## Test

```bash
pytest
ruff check mf_app scripts tests
```

Tests embed the **real** backend FastAPI app in-process (`httpx.ASGITransport`,
same technique as `sdk/tests/`) so every institution onboarded in the test suite
goes through real routing/validation/DB on both sides — this is what proves the
dogfooding claim in automated tests, not just in a manual live smoke test. Two
things are faked, matching the project-wide precedent of mocking the agent in
fast automated suites and reserving real Docker Postgres for a manual
live-verification pass: `app.services.orchestrator.call_agent` (backend) and
`mf_app.db.tenant_session.tenant_database_url` (a real local SQLite file stands
in for a real Postgres per institution — the actual Alembic migration subprocess
still genuinely runs, just against SQLite).

Running these tests needs **both** `microfinance/requirements.txt` and
`backend/requirements.txt` installed into `microfinance/.venv` (the embedded
backend needs its own dependencies, e.g. `pyotp`) — see `tests/conftest.py`'s
docstring for the full reasoning, including why the package had to be renamed
from `app` to `mf_app` in the first place (the exact `tests`-package collision
class of bug Phase 8 found, one level up).

Two real bugs found by these tests, both documented in detail in
`docs/architecture/08-microfinance-et-billing.md` §8.13:
- `MFPlatformAccount.token_expires_at`, read back from a fresh SQLite session
  (the second institution onboarded in a given process), came back
  timezone-naive and crashed comparing it against a fresh `utcnow()` — SQLite
  doesn't round-trip `tzinfo` (cf. `mf_app/core/timeutil.py`'s docstring, the
  same documented pitfall as the backend's). Fixed with `as_aware_utc()` in
  `mf_app/services/platform_client.py`.
- A background `asyncio.Task` ticking the backend's job worker *concurrently*
  with the microfinance job's own `wait_for_job()` poll loop intermittently hit
  `OperationalError: cannot commit transaction - SQL statements in progress`
  on the shared in-memory SQLite connection once enough institutions were
  onboarded in one test session (invisible at 9.1's scale, real at 9.2's).
  Fixed by ticking the backend worker synchronously, in the same coroutine,
  from inside `PlatformClient.wait_for_job` itself — removes the race instead
  of narrowing it, and made the whole suite ~5x faster as a side effect.

## Layout

```
mf_app/
  core/       settings, staff password hashing, staff JWT, operator token
  db/         GUID type; control_*.py (Control DB) and tenant_*.py (per-institution DB)
  models/     MFPlatformAccount, MFInstitution, MFStaffUser, MFJob (control);
              models/tenant/ (Branch, Agent, Customer, InternalAccount,
              SavingsProduct/Account, Transaction/LedgerEntry, LoanProduct,
              Loan, RepaymentSchedule/Line — the tenant schema)
  schemas/    Pydantic request/response models
  services/   platform_client (SDK wrapper), onboarding (job handler),
              tenant_migrate (Alembic subprocess), jobs (queue), rbac, secrets,
              ledger (double-entry engine), savings, amortization, loans,
              reports, payments (provider abstraction)
  api/v1/     institutions (operator-only onboarding), auth, branches, staff,
              customers, savings, loans, reports, jobs
scripts/      bootstrap_platform_account, generate_operator_token
alembic_control/  migrations for this service's own metadata DB
alembic_tenant/   migrations applied to every institution's own database
tests/        pytest + embedded real backend, one file per concern
```
