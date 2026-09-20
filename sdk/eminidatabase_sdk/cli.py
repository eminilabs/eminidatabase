"""`platform` CLI — cf. docs/architecture/07-api-cli-sdk.md §7.2 and cahier des
charges §51. Every command is a thin wrapper over PlatformClient: the CLI carries
no logic the SDK doesn't already have, other than argument parsing, local
credential storage, and resolving a human-friendly slug/name to the UUID the API
actually wants.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

import typer

from eminidatabase_sdk.auth_store import clear_credentials, load_credentials, save_credentials
from eminidatabase_sdk.client import DEFAULT_BASE_URL, PlatformClient
from eminidatabase_sdk.exceptions import ApiError

app = typer.Typer(help="eminidatabase CLI — manage your Cloud Database Platform resources.")
organizations_app = typer.Typer(help="Manage organizations")
projects_app = typer.Typer(help="Manage projects")
db_app = typer.Typer(help="Manage databases")
backup_app = typer.Typer(help="Manage database backups")
jobs_app = typer.Typer(help="Inspect asynchronous jobs")
webhooks_app = typer.Typer(help="Manage webhooks")

app.add_typer(organizations_app, name="organizations")
app.add_typer(projects_app, name="projects")
app.add_typer(db_app, name="db")
db_app.add_typer(backup_app, name="backup")
app.add_typer(jobs_app, name="jobs")
app.add_typer(webhooks_app, name="webhooks")


def _print(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


def _run(coro):
    try:
        return asyncio.run(coro)
    except ApiError as exc:
        typer.echo(f"Error: {exc.detail}", err=True)
        raise typer.Exit(1) from exc


def _authenticated_client() -> PlatformClient:
    creds = load_credentials()
    if creds is None:
        typer.echo("Not logged in. Run `platform login` first.", err=True)
        raise typer.Exit(1)
    base_url = os.environ.get("EMINIDATABASE_API_URL", creds["base_url"])
    return PlatformClient(base_url=base_url, token=creds["token"])


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


async def _resolve_organization(client: PlatformClient, ref: str) -> dict:
    if _is_uuid(ref):
        return await client.get_organization(ref)
    for org in await client.list_organizations():
        if org["slug"] == ref:
            return org
    typer.echo(f"No organization found matching {ref!r}", err=True)
    raise typer.Exit(1)


async def _resolve_project(client: PlatformClient, organization_id: str, ref: str) -> dict:
    if _is_uuid(ref):
        return await client.get_project(organization_id, ref)
    for project in await client.list_projects(organization_id):
        if project["slug"] == ref:
            return project
    typer.echo(f"No project found matching {ref!r}", err=True)
    raise typer.Exit(1)


async def _resolve_database(
    client: PlatformClient, organization_id: str, project_id: str, ref: str
) -> dict:
    if _is_uuid(ref):
        return await client.get_database(organization_id, project_id, ref)
    for database in await client.list_databases(organization_id, project_id):
        if database["name"] == ref:
            return database
    typer.echo(f"No database found matching {ref!r}", err=True)
    raise typer.Exit(1)


# --- Auth -----------------------------------------------------------------


@app.command()
def login(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
    api_url: str = typer.Option(DEFAULT_BASE_URL, "--api-url", envvar="EMINIDATABASE_API_URL"),
    otp: str | None = typer.Option(None, "--otp", help="TOTP code, if MFA is enabled"),
) -> None:
    async def go():
        client = PlatformClient(base_url=api_url)
        token = await client.login(email, password, otp)
        save_credentials(api_url, email, token)
        typer.echo(f"Logged in as {email} ({api_url})")

    _run(go())


@app.command()
def logout() -> None:
    clear_credentials()
    typer.echo("Logged out.")


@app.command()
def whoami() -> None:
    async def go():
        _print(await _authenticated_client().me())

    _run(go())


# --- Organizations ----------------------------------------------------------


@organizations_app.command("create")
def organizations_create(name: str, slug: str) -> None:
    async def go():
        _print(await _authenticated_client().create_organization(name, slug))

    _run(go())


@organizations_app.command("list")
def organizations_list() -> None:
    async def go():
        _print(await _authenticated_client().list_organizations())

    _run(go())


# --- Projects -------------------------------------------------------------


@projects_app.command("create")
def projects_create(organization: str, name: str, slug: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        _print(await client.create_project(org["id"], name, slug))

    _run(go())


@projects_app.command("list")
def projects_list(organization: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        _print(await client.list_projects(org["id"]))

    _run(go())


# --- Databases --------------------------------------------------------------


@db_app.command("create")
def db_create(
    organization: str,
    project: str,
    name: str,
    region: str = typer.Option(..., "--region"),
    cpu: int = typer.Option(1, "--cpu"),
    ram: int = typer.Option(1024, "--ram", help="RAM in MB"),
    storage: int = typer.Option(10, "--storage", help="Storage in GB"),
    isolation: str = typer.Option("shared", "--isolation"),
    wait: bool = typer.Option(False, "--wait", help="Wait for provisioning to finish"),
) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        result = await client.create_database(
            org["id"],
            proj["id"],
            name,
            region,
            isolation_level=isolation,
            cpu_limit=cpu,
            ram_limit_mb=ram,
            storage_limit_gb=storage,
        )
        if wait:
            typer.echo(f"Waiting for job {result['job_id']}...", err=True)
            await client.wait_for_job(result["job_id"])
            result["database"] = await client.get_database(
                org["id"], proj["id"], result["database"]["id"]
            )
        _print(result)

    _run(go())


@db_app.command("list")
def db_list(organization: str, project: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        _print(await client.list_databases(org["id"], proj["id"]))

    _run(go())


@db_app.command("get")
def db_get(organization: str, project: str, name: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        _print(await _resolve_database(client, org["id"], proj["id"], name))

    _run(go())


@db_app.command("connect")
def db_connect(organization: str, project: str, name: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        _print(await client.get_connection(org["id"], proj["id"], database["id"]))

    _run(go())


@db_app.command("delete")
def db_delete(organization: str, project: str, name: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        _print(await client.delete_database(org["id"], proj["id"], database["id"]))

    _run(go())


@db_app.command("suspend")
def db_suspend(organization: str, project: str, name: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        _print(await client.suspend_database(org["id"], proj["id"], database["id"]))

    _run(go())


@db_app.command("resume")
def db_resume(organization: str, project: str, name: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        _print(await client.resume_database(org["id"], proj["id"], database["id"]))

    _run(go())


@db_app.command("resize")
def db_resize(
    organization: str,
    project: str,
    name: str,
    cpu: int = typer.Option(..., "--cpu"),
    ram: int = typer.Option(..., "--ram", help="RAM in MB"),
    storage: int = typer.Option(..., "--storage", help="Storage in GB"),
) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        _print(
            await client.resize_database(
                org["id"],
                proj["id"],
                database["id"],
                cpu_limit=cpu,
                ram_limit_mb=ram,
                storage_limit_gb=storage,
            )
        )

    _run(go())


@db_app.command("sql")
def db_sql(organization: str, project: str, name: str, query: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        _print(await client.execute_sql(org["id"], proj["id"], database["id"], query))

    _run(go())


# --- Backups ----------------------------------------------------------------


@backup_app.command("create")
def backup_create(
    organization: str,
    project: str,
    name: str,
    wait: bool = typer.Option(False, "--wait"),
) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        result = await client.create_backup(org["id"], proj["id"], database["id"])
        if wait:
            typer.echo(f"Waiting for job {result['job_id']}...", err=True)
            await client.wait_for_job(result["job_id"])
            result["backup"] = await client.get_backup(
                org["id"], proj["id"], database["id"], result["backup"]["id"]
            )
        _print(result)

    _run(go())


@backup_app.command("list")
def backup_list(organization: str, project: str, name: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        _print(await client.list_backups(org["id"], proj["id"], database["id"]))

    _run(go())


@db_app.command("restore")
def db_restore(
    organization: str,
    project: str,
    name: str,
    backup_id: str,
    new_name: str,
    wait: bool = typer.Option(False, "--wait"),
) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        proj = await _resolve_project(client, org["id"], project)
        database = await _resolve_database(client, org["id"], proj["id"], name)
        result = await client.restore_backup(
            org["id"], proj["id"], database["id"], backup_id, new_name
        )
        if wait:
            typer.echo(f"Waiting for job {result['job_id']}...", err=True)
            await client.wait_for_job(result["job_id"])
            result["database"] = await client.get_database(
                org["id"], proj["id"], result["database"]["id"]
            )
        _print(result)

    _run(go())


# --- Webhooks ---------------------------------------------------------------


@webhooks_app.command("create")
def webhooks_create(
    organization: str,
    url: str,
    event_types: list[str] = typer.Argument(..., help="e.g. database.created backup.completed"),
) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        _print(await client.create_webhook(org["id"], url, event_types))

    _run(go())


@webhooks_app.command("list")
def webhooks_list(organization: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        _print(await client.list_webhooks(org["id"]))

    _run(go())


@webhooks_app.command("delete")
def webhooks_delete(organization: str, webhook_id: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        _print(await client.delete_webhook(org["id"], webhook_id))

    _run(go())


@webhooks_app.command("deliveries")
def webhooks_deliveries(organization: str, webhook_id: str) -> None:
    async def go():
        client = _authenticated_client()
        org = await _resolve_organization(client, organization)
        _print(await client.list_webhook_deliveries(org["id"], webhook_id))

    _run(go())


# --- Jobs -------------------------------------------------------------------


@jobs_app.command("get")
def jobs_get(job_id: str) -> None:
    async def go():
        _print(await _authenticated_client().get_job(job_id))

    _run(go())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
