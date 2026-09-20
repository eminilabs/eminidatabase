import socket
from functools import lru_cache
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    control_plane_url: str = "http://127.0.0.1:8000/api/v1"
    bootstrap_token: str | None = None
    region_code: str = "eu-west"
    hostname: str = ""
    ip_address: str | None = None
    agent_port: int = 9443
    heartbeat_interval_seconds: int = 20
    state_dir: str = "./state"
    agent_version: str = "0.1.0"

    # The Postgres instance this agent manages, and the admin DSN it uses to issue
    # CREATE DATABASE/ROLE etc. In production these point at the same local
    # PostgreSQL running on this node; in this sandbox they point at whatever
    # container/instance is standing in for "this node's Postgres".
    postgres_port: int = 5432
    postgres_admin_dsn: str = "postgresql://postgres:postgres@127.0.0.1:5432/postgres"

    # pg_dump/pg_restore run as subprocesses. In production these are plain local
    # binaries (PostgreSQL client tools ship alongside the server on the VPS) and
    # pg_dump_command_prefix is empty. In this sandbox, "this node's Postgres" is a
    # Docker container without host-installed client tools, so the prefix routes
    # the same commands through `docker exec` into the container — and, because
    # that runs *inside* the container's network namespace, pg_dump_host/port then
    # point at Postgres's in-container address rather than the host-mapped one.
    pg_dump_path: str = "pg_dump"
    pg_restore_path: str = "pg_restore"
    # comma-separated, e.g. "docker,exec,-i,eminidb-node-postgres" — the `-i` is
    # not optional: pg_restore reads its dump from stdin, and `docker exec`
    # silently drops stdin without it (pg_dump never notices, since it only
    # writes to stdout — a real Phase 11 bug: an `.env` missing `-i` created a
    # dump that "succeeded" and reported a real byte count, but every restore/
    # verify against it failed with "input file is too short (read 0,
    # expected 5)", since pg_restore's stdin was silently empty).
    pg_dump_command_prefix: str = ""
    pg_dump_host: str = "127.0.0.1"
    pg_dump_port: int = 5432

    # Backups are encrypted (Fernet) before they ever leave this process — cf.
    # backend/app/services/secrets.py for the same pattern applied to credentials.
    # Dev-only default; override in any real deployment, ideally via KMS.
    backup_encryption_key: str = "08u_J80OTnrWkefxT-D4WVGWAnX-CJynJWy-T-SCvXQ="

    # S3-compatible object storage (MinIO in dev, per Règle: never the same disk as
    # the primary database).
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "eminidatabase-backups"
    s3_region: str = "us-east-1"

    def dump_command_prefix(self) -> list[str]:
        return [p for p in self.pg_dump_command_prefix.split(",") if p]

    def admin_credentials(self) -> tuple[str, str]:
        parsed = urlparse(self.postgres_admin_dsn)
        return parsed.username or "postgres", parsed.password or ""

    def resolved_hostname(self) -> str:
        return self.hostname or socket.gethostname()


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
