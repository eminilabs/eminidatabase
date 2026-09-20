"""Official Python client for the eminidatabase Control Plane API.

cf. docs/architecture/07-api-cli-sdk.md — "La CLI doit utiliser l'API officielle",
via this SDK, so CLI and SDK never carry duplicated request-building logic (the CLI
in this package's own `cli.py` is built entirely on top of `PlatformClient`).

Every method is a thin wrapper around one API call: no client-side business logic,
no caching, no retries — those all live in the platform itself (see the backend's
own job/retry machinery). This keeps the SDK trivially easy to keep in sync with
the API surface and to port to another language later.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from eminidatabase_sdk.exceptions import ApiError

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
TERMINAL_JOB_STATUSES = {"succeeded", "failed"}


class PlatformClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._transport = transport
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            transport=self._transport,
            timeout=self._timeout,
        ) as client:
            resp = await client.request(method, path, **kwargs)

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise ApiError(resp.status_code, detail)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # --- Auth ---------------------------------------------------------

    async def register(self, email: str, password: str) -> dict:
        return await self._request(
            "POST", "/auth/register", json={"email": email, "password": password}
        )

    async def login(self, email: str, password: str, otp_code: str | None = None) -> str:
        body: dict[str, Any] = {"email": email, "password": password}
        if otp_code:
            body["otp_code"] = otp_code
        data = await self._request("POST", "/auth/login", json=body)
        self.token = data["access_token"]
        return self.token

    async def me(self) -> dict:
        return await self._request("GET", "/auth/me")

    # --- Organizations --------------------------------------------------

    async def create_organization(self, name: str, slug: str) -> dict:
        return await self._request("POST", "/organizations", json={"name": name, "slug": slug})

    async def list_organizations(self) -> list[dict]:
        return await self._request("GET", "/organizations")

    async def get_organization(self, organization_id: str) -> dict:
        return await self._request("GET", f"/organizations/{organization_id}")

    async def add_member(self, organization_id: str, email: str, role: str = "developer") -> dict:
        return await self._request(
            "POST",
            f"/organizations/{organization_id}/members",
            json={"email": email, "role": role},
        )

    # --- Projects ---------------------------------------------------------

    async def create_project(self, organization_id: str, name: str, slug: str) -> dict:
        return await self._request(
            "POST", f"/organizations/{organization_id}/projects", json={"name": name, "slug": slug}
        )

    async def list_projects(self, organization_id: str) -> list[dict]:
        return await self._request("GET", f"/organizations/{organization_id}/projects")

    async def get_project(self, organization_id: str, project_id: str) -> dict:
        return await self._request(
            "GET", f"/organizations/{organization_id}/projects/{project_id}"
        )

    # --- Regions ------------------------------------------------------

    async def list_regions(self) -> list[dict]:
        return await self._request("GET", "/regions")

    # --- Databases ------------------------------------------------------

    def _db_path(self, organization_id: str, project_id: str, database_id: str = "") -> str:
        base = f"/organizations/{organization_id}/projects/{project_id}/databases"
        return f"{base}/{database_id}" if database_id else base

    async def create_database(
        self,
        organization_id: str,
        project_id: str,
        name: str,
        region_code: str,
        *,
        isolation_level: str = "shared",
        cpu_limit: int = 1,
        ram_limit_mb: int = 1024,
        storage_limit_gb: int = 10,
    ) -> dict:
        payload = {
            "name": name,
            "region_code": region_code,
            "isolation_level": isolation_level,
            "cpu_limit": cpu_limit,
            "ram_limit_mb": ram_limit_mb,
            "storage_limit_gb": storage_limit_gb,
        }
        return await self._request(
            "POST", self._db_path(organization_id, project_id), json=payload
        )

    async def list_databases(self, organization_id: str, project_id: str) -> list[dict]:
        return await self._request("GET", self._db_path(organization_id, project_id))

    async def get_database(self, organization_id: str, project_id: str, database_id: str) -> dict:
        return await self._request(
            "GET", self._db_path(organization_id, project_id, database_id)
        )

    async def delete_database(
        self, organization_id: str, project_id: str, database_id: str
    ) -> dict:
        return await self._request(
            "DELETE", self._db_path(organization_id, project_id, database_id)
        )

    async def suspend_database(
        self, organization_id: str, project_id: str, database_id: str
    ) -> dict:
        return await self._request(
            "POST", self._db_path(organization_id, project_id, database_id) + "/suspend"
        )

    async def resume_database(
        self, organization_id: str, project_id: str, database_id: str
    ) -> dict:
        return await self._request(
            "POST", self._db_path(organization_id, project_id, database_id) + "/resume"
        )

    async def resize_database(
        self,
        organization_id: str,
        project_id: str,
        database_id: str,
        *,
        cpu_limit: int,
        ram_limit_mb: int,
        storage_limit_gb: int,
    ) -> dict:
        payload = {
            "cpu_limit": cpu_limit,
            "ram_limit_mb": ram_limit_mb,
            "storage_limit_gb": storage_limit_gb,
        }
        return await self._request(
            "POST",
            self._db_path(organization_id, project_id, database_id) + "/resize",
            json=payload,
        )

    async def get_connection(
        self, organization_id: str, project_id: str, database_id: str
    ) -> dict:
        return await self._request(
            "GET", self._db_path(organization_id, project_id, database_id) + "/connection"
        )

    async def execute_sql(
        self,
        organization_id: str,
        project_id: str,
        database_id: str,
        query: str,
        *,
        role_id: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"query": query}
        if role_id:
            payload["role_id"] = role_id
        return await self._request(
            "POST",
            self._db_path(organization_id, project_id, database_id) + "/sql/execute",
            json=payload,
        )

    # --- Backups ------------------------------------------------------

    async def create_backup(
        self, organization_id: str, project_id: str, database_id: str
    ) -> dict:
        return await self._request(
            "POST", self._db_path(organization_id, project_id, database_id) + "/backups"
        )

    async def list_backups(
        self, organization_id: str, project_id: str, database_id: str
    ) -> list[dict]:
        return await self._request(
            "GET", self._db_path(organization_id, project_id, database_id) + "/backups"
        )

    async def get_backup(
        self, organization_id: str, project_id: str, database_id: str, backup_id: str
    ) -> dict:
        return await self._request(
            "GET",
            self._db_path(organization_id, project_id, database_id) + f"/backups/{backup_id}",
        )

    async def restore_backup(
        self,
        organization_id: str,
        project_id: str,
        database_id: str,
        backup_id: str,
        new_name: str,
    ) -> dict:
        return await self._request(
            "POST",
            self._db_path(organization_id, project_id, database_id)
            + f"/backups/{backup_id}/restore",
            json={"name": new_name},
        )

    # --- Webhooks -----------------------------------------------------

    async def create_webhook(self, organization_id: str, url: str, event_types: list[str]) -> dict:
        return await self._request(
            "POST",
            f"/organizations/{organization_id}/webhooks",
            json={"url": url, "event_types": event_types},
        )

    async def list_webhooks(self, organization_id: str) -> list[dict]:
        return await self._request("GET", f"/organizations/{organization_id}/webhooks")

    async def delete_webhook(self, organization_id: str, webhook_id: str) -> dict:
        return await self._request(
            "DELETE", f"/organizations/{organization_id}/webhooks/{webhook_id}"
        )

    async def list_webhook_deliveries(self, organization_id: str, webhook_id: str) -> list[dict]:
        return await self._request(
            "GET", f"/organizations/{organization_id}/webhooks/{webhook_id}/deliveries"
        )

    # --- Jobs -----------------------------------------------------------

    async def get_job(self, job_id: str) -> dict:
        return await self._request("GET", f"/jobs/{job_id}")

    async def wait_for_job(
        self, job_id: str, *, interval: float = 1.0, timeout: float = 120.0
    ) -> dict:
        start = time.monotonic()
        while True:
            job = await self.get_job(job_id)
            if job["status"] in TERMINAL_JOB_STATUSES:
                return job
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
            await asyncio.sleep(interval)
