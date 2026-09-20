# Data Plane Agent (Phases 2-7)

Runs on every node of the Data Plane. Registers itself with the Control Plane over
a one-shot bootstrap token, then exposes an HTTPS API that **only the Control Plane
can call**, authenticated by mutual TLS using an internal CA the Control Plane
manages (`backend/app/services/ca.py`). See
[../docs/architecture/03-database-orchestrator-et-agent.md](../docs/architecture/03-database-orchestrator-et-agent.md).

Phase 2: registration, heartbeat, `/v1/health`, `/v1/resources`. Phase 3 adds actual
PostgreSQL provisioning (`app/postgres_admin.py`): `POST /v1/provision/database`,
`DELETE /v1/database/{name}`, `POST /v1/database/{name}/{suspend,resume}` — this is
the only code in the whole platform that runs `CREATE`/`DROP DATABASE`/`ROLE`. Phase
4 adds additional roles (`POST/DELETE /v1/database/{name}/roles/...`, `.../rotate`),
an extensions allowlist (`.../extensions`), metrics (`.../metrics`), and schema
introspection (`.../tables`). Phase 5 adds backups (`app/backup.py`): real
`pg_dump`/`pg_restore` subprocesses, Fernet encryption before anything reaches
object storage, and `POST .../backup`, `POST .../restore`, `POST /v1/verify-backup`,
`DELETE /v1/backups`. Phase 6 adds replication status and promotion
(`app/replication.py`): `GET /v1/replication/status`, `POST /v1/replication/promote`.
Phase 7 adds vertical resize (`POST .../connection-limit`) and migration quiescing
(`POST .../quiesce`) — the latter took three attempts to get right (see
`postgres_admin.quiesce_for_migration`'s docstring and
`docs/architecture/09-plan-de-phases.md` Phase 7 for the full story: naive
approaches kept leaving either the admin's own dump connection or the tenant's
owner role able to connect).

## Backups: pg_dump/pg_restore and object storage

Add to `.env` (see `.env.example` for the full set, including the `docker exec`
bridge this sandbox uses since "this node's Postgres" is a container without host
client tools):

```
PG_DUMP_COMMAND_PREFIX=
PG_DUMP_HOST=127.0.0.1
PG_DUMP_PORT=5432
BACKUP_ENCRYPTION_KEY=<generate with the snippet in .env.example>
S3_ENDPOINT_URL=http://127.0.0.1:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=eminidatabase-backups
```

For local development, MinIO stands in for the S3-compatible object storage:

```bash
docker run -d --name eminidb-minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

## PostgreSQL this agent manages

In production this points at the PostgreSQL running locally on the same VPS. Set in
`.env`:

```
POSTGRES_PORT=5432
POSTGRES_ADMIN_DSN=postgresql://postgres:postgres@127.0.0.1:5432/postgres
```

For local development/testing without a real VPS, any reachable PostgreSQL works,
e.g. a container:

```bash
docker run -d --name eminidb-node-postgres -e POSTGRES_PASSWORD=postgres -p 5544:5432 postgres:16-alpine
```
then `POSTGRES_ADMIN_DSN=postgresql://postgres:postgres@127.0.0.1:5544/postgres` and
`POSTGRES_PORT=5544` (this is also what `postgres_port` reports to the Control
Plane, so client connection strings it returns point at the right port).

## Setup

```bash
cd agent
python -m venv .venv
./.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

## First-time registration (once per node)

1. On the Control Plane, a platform admin creates a region (if needed) and a
   one-shot bootstrap token:
   ```bash
   curl -X POST $CP/api/v1/regions -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"code":"eu-west","name":"Europe West"}'
   curl -X POST $CP/api/v1/nodes/registration-tokens -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"region_code":"eu-west","note":"vps-01"}'
   ```
2. On the node, set `CONTROL_PLANE_URL`, `BOOTSTRAP_TOKEN`, `REGION_CODE`,
   `IP_ADDRESS` (the address the Control Plane will use to reach this node) in `.env`,
   then run:
   ```bash
   python bootstrap.py
   ```
   This saves `node.key`, `node.crt`, `ca.crt`, and the node's credentials under
   `STATE_DIR` (default `./state`). The bootstrap token is single-use — the script
   fails if you try to run it twice against an already-registered node.

## Running the agent

```bash
uvicorn app.main:app --host 0.0.0.0 --port 9443 \
  --ssl-keyfile ./state/node.key --ssl-certfile ./state/node.crt \
  --ssl-ca-certs ./state/ca.crt --ssl-cert-reqs 2
```

`--ssl-cert-reqs 2` (`CERT_REQUIRED`) means the server rejects any connection that
doesn't present a client certificate signed by the same CA — this is what makes it
mTLS rather than plain TLS. The Control Plane presents its own certificate
(auto-generated on first use under `backend/certs/control-plane.{key,crt}`) when it
calls this agent — e.g. via `POST /api/v1/nodes/{id}/health-check` on the Control
Plane, which performs exactly this call.

On startup the agent also begins sending periodic heartbeats
(`HEARTBEAT_INTERVAL_SECONDS`, default 20s) back to the Control Plane over its
regular HTTPS API, authenticated with the node secret issued at registration — this
direction does not use mTLS since it hits the Control Plane's normal public-ish API,
not a private per-node listener (cf. docs/architecture §"Sécurité de la
communication").

## High availability: setting up a real streaming replica (Phase 6)

Replica *provisioning* is a one-time infrastructure bootstrap step (cf.
`app/replication.py`'s docstring) — in production the agent runs on the same VPS as
Postgres and has real `pg_ctl`/systemd control, so this would be automated as part
of bringing up a new standby node from day one. In this Docker-based sandbox,
Docker (not the agent) owns the Postgres process lifecycle, so the clone is done
once via plain Docker commands, exactly like the initial Postgres/MinIO containers:

```bash
# 1. Put the primary on a network the replica can reach it through by name.
docker network create eminidb-net
docker network connect eminidb-net eminidb-node-postgres

# 2. Create a replication role and allow it in from the network.
docker exec eminidb-node-postgres psql -U postgres -c \
  "CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'replicator-pass';"
docker exec eminidb-node-postgres sh -c \
  "echo 'host replication replicator all scram-sha-256' >> /var/lib/postgresql/data/pg_hba.conf"
docker exec eminidb-node-postgres psql -U postgres -c "SELECT pg_reload_conf();"

# 3. Clone the primary. -R writes standby.signal + primary_conninfo automatically.
docker volume create eminidb-replica-data
docker run --rm --network eminidb-net -v eminidb-replica-data:/var/lib/postgresql/data \
  -e PGPASSWORD=replicator-pass postgres:16-alpine \
  pg_basebackup -h eminidb-node-postgres -p 5432 -U replicator \
    -D /var/lib/postgresql/data -Fp -Xs -P -R

# 4. pg_basebackup ran as root in the temporary container — fix ownership before
#    Postgres will start against this data directory.
docker run --rm -v eminidb-replica-data:/var/lib/postgresql/data postgres:16-alpine \
  chown -R postgres:postgres /var/lib/postgresql/data
docker run --rm -v eminidb-replica-data:/var/lib/postgresql/data postgres:16-alpine \
  chmod 700 /var/lib/postgresql/data

# 5. Start it — the entrypoint sees an already-initialized data dir (with
#    standby.signal) and starts Postgres directly in standby/recovery mode.
docker run -d --name eminidb-node-postgres-replica --network eminidb-net \
  -v eminidb-replica-data:/var/lib/postgresql/data -p 5545:5432 postgres:16-alpine
```

Then bootstrap and run a second agent against it exactly like the primary's (see
above), pointing `POSTGRES_PORT`/`POSTGRES_ADMIN_DSN` at `5545` and using a
different `AGENT_PORT`/`STATE_DIR` — see
`docs/architecture/09-plan-de-phases.md` (Phase 6) for the full two-agent failover
walkthrough. **Promoting this replica (via the Control Plane's failover, or
`POST /v1/replication/promote` directly) permanently detaches it — rebuilding
replication means repeating this bootstrap.**

## Test

```bash
pytest
ruff check app tests bootstrap.py
```

CSR generation, resource collection, and RBAC-adjacent identifier validation are
unit tested with no live sockets. `tests/test_postgres_admin.py`, `test_backup.py`,
and `test_replication.py` are real integration tests — they connect to an actual
PostgreSQL (`POSTGRES_TEST_PORT`, default 5544) and, for replication, its standby
(`POSTGRES_REPLICA_TEST_PORT`, default 5545 — see "setting up a real streaming
replica" above); they skip gracefully if these aren't reachable rather than failing
the suite. `test_replication.py`'s promotion test is additionally skipped unless
`RUN_DESTRUCTIVE_HA_TESTS=1` is set, since promoting the replica permanently
detaches it from the primary (the live Phase 6 smoke test exercises this path
deliberately instead — see `docs/architecture/09-plan-de-phases.md`). The mTLS
handshake itself, and the full create → connect → suspend → resume → delete →
backup → restore → failover cycle through the real Control Plane + worker +
scheduler, are verified manually (see the Phase 2/3/5/6 completion notes in
`../docs/architecture/09-plan-de-phases.md`) since they require several real running
processes and real sockets, which doesn't belong in a unit test suite.
