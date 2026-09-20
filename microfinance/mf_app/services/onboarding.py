"""Institution onboarding — the job handler behind POST /institutions.

Dogfoods the Phase 8 Python SDK exactly like a third-party developer would (cf.
docs/architecture/08 §8.3/§8.4): create a project + database on the platform,
wait for it to come up, fetch its connection, apply the tenant schema, then mark
the institution ACTIVE.

Deliberately a job, not inline in the API request: provisioning a database is a
multi-second/multi-minute operation end to end (create → wait_for_job → connect →
migrate), squarely the kind of "long operation" that must never block an HTTP
request (cf. the platform's own Règle for async jobs, §54).

The institution_admin staff account and its one-time password are created
SYNCHRONOUSLY in the API endpoint instead (app/api/v1/endpoints/institutions.py),
not here — generating a secret inside an async job would mean persisting it
somewhere (job.result) to hand back to the caller later, which is exactly the
plaintext-secret-at-rest this codebase avoids everywhere else (cf. how API keys
and webhook secrets are always revealed once, synchronously, never re-readable).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mf_app.db.tenant_session import get_tenant_engine, tenant_database_url
from mf_app.models.institution import MFInstitution, MFInstitutionStatus
from mf_app.models.job import MFJob
from mf_app.models.tenant.institution_profile import InstitutionProfile
from mf_app.models.tenant.internal_account import InternalAccount
from mf_app.services.platform_client import get_authenticated_client, get_platform_account
from mf_app.services.secrets import encrypt_secret
from mf_app.services.tenant_migrate import run_tenant_migrations


async def execute_onboard_institution(db: AsyncSession, job: MFJob) -> dict:
    institution = await db.get(MFInstitution, uuid.UUID(job.payload["institution_id"]))
    if institution is None:
        raise RuntimeError(f"MFInstitution {job.payload['institution_id']} not found")

    region_code = job.payload["region_code"]
    currency = job.payload["currency"]

    client = await get_authenticated_client(db)
    account = await get_platform_account(db)

    project = await client.create_project(
        str(account.cp_organization_id), institution.name, institution.slug
    )
    create_result = await client.create_database(
        str(account.cp_organization_id), project["id"], "main", region_code
    )
    await client.wait_for_job(create_result["job_id"])
    database = await client.get_database(
        str(account.cp_organization_id), project["id"], create_result["database"]["id"]
    )
    connection = await client.get_connection(
        str(account.cp_organization_id), project["id"], database["id"]
    )

    institution.cp_project_id = uuid.UUID(project["id"])
    institution.cp_database_id = uuid.UUID(database["id"])
    institution.db_host = connection["host"]
    institution.db_port = connection["port"]
    institution.db_name = connection["database"]
    institution.db_username = connection["username"]
    institution.encrypted_db_password = encrypt_secret(connection["password"])
    await db.flush()

    tenant_url = tenant_database_url(institution)
    await run_tenant_migrations(tenant_url)

    tenant_session_factory = async_sessionmaker(
        bind=get_tenant_engine(tenant_url), expire_on_commit=False
    )
    async with tenant_session_factory() as tenant_db:
        tenant_db.add(InstitutionProfile(name=institution.name, currency=currency))
        # InternalAccounts every institution needs from day one (§8.7): "cash"
        # is the ledger's till/vault leg for every deposit/withdrawal/
        # disbursement/repayment (asset, debit increases it); "interest_income"
        # is where loan interest repayments post to (revenue, credit increases
        # it) — needed as soon as the first loan product exists (Phase 9.3).
        tenant_db.add(InternalAccount(name="cash", normal_balance_side="debit"))
        tenant_db.add(InternalAccount(name="interest_income", normal_balance_side="credit"))
        await tenant_db.commit()

    institution.status = MFInstitutionStatus.ACTIVE
    await db.flush()

    return {"cp_project_id": str(institution.cp_project_id)}


MF_HANDLERS = {"onboard_institution": execute_onboard_institution}
