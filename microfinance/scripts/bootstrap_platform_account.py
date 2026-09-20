"""One-time setup: registers this microfinance service as a single Control Plane
client (cf. docs/architecture/08 §8.3/§8.4) — one CP user, one CP organization,
reused for every institution this service ever onboards. Refuses to run twice
(a second MFPlatformAccount would be ambiguous — which one does onboarding use?).

Usage:
    python -m scripts.bootstrap_platform_account <email> <password> <org-name> <org-slug>
"""

from __future__ import annotations

import asyncio
import sys

from eminidatabase_sdk import PlatformClient
from sqlalchemy import select

from mf_app.core.config import get_settings
from mf_app.db.control_session import AsyncSessionLocal
from mf_app.models.platform_account import MFPlatformAccount
from mf_app.services.secrets import encrypt_secret


async def bootstrap(email: str, password: str, org_name: str, org_slug: str) -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(MFPlatformAccount))).scalars().first()
        if existing is not None:
            print("An MFPlatformAccount already exists — refusing to create a second one.",
                  file=sys.stderr)
            raise SystemExit(1)

        client = PlatformClient(base_url=get_settings().platform_api_url)
        await client.register(email, password)
        await client.login(email, password)
        org = await client.create_organization(org_name, org_slug)

        db.add(
            MFPlatformAccount(
                cp_organization_id=org["id"],
                cp_email=email,
                encrypted_cp_password=encrypt_secret(password),
                # Left unset on purpose: app/services/platform_client.py logs in
                # fresh the first time it's asked for a client, rather than
                # trusting a token minted outside its own refresh bookkeeping.
                cached_access_token=None,
                token_expires_at=None,
            )
        )
        await db.commit()
        print(f"Bootstrapped MFPlatformAccount for organization {org_name!r} ({org['id']}).")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            "Usage: python -m scripts.bootstrap_platform_account "
            "<email> <password> <org-name> <org-slug>",
            file=sys.stderr,
        )
        raise SystemExit(1)
    asyncio.run(bootstrap(*sys.argv[1:5]))
