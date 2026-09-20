"""Builds an authenticated PlatformClient for this service's own, single
Control Plane identity (MFPlatformAccount) — re-logging in when the cached token
is near expiry. Every institution's project+database is created through this one
client, exactly like any third-party developer would use the SDK (cf.
docs/architecture/08 §8.3 — this service dogfoods the Phase 8 Python SDK)."""

from __future__ import annotations

import datetime as dt

from eminidatabase_sdk import PlatformClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mf_app.core.config import get_settings
from mf_app.core.timeutil import as_aware_utc, utcnow
from mf_app.models.platform_account import MFPlatformAccount
from mf_app.services.secrets import decrypt_secret

_TOKEN_REFRESH_MARGIN = dt.timedelta(minutes=1)


async def get_platform_account(db: AsyncSession) -> MFPlatformAccount:
    account = (await db.execute(select(MFPlatformAccount))).scalars().first()
    if account is None:
        raise RuntimeError(
            "No MFPlatformAccount configured — run "
            "`python -m scripts.bootstrap_platform_account` first."
        )
    return account


async def get_authenticated_client(db: AsyncSession) -> PlatformClient:
    account = await get_platform_account(db)
    settings = get_settings()
    client = PlatformClient(base_url=settings.platform_api_url)

    needs_login = (
        account.cached_access_token is None
        or account.token_expires_at is None
        # SQLite (used in tests) doesn't round-trip tzinfo — a token_expires_at
        # read back from a fresh session can come back naive even though it was
        # written as timezone-aware (cf. core/timeutil.py's docstring), so it
        # must be normalized before comparing against a freshly created aware
        # utcnow(). A real bug found here: the second institution onboarded in a
        # given process hit this exact TypeError on token refresh.
        or as_aware_utc(account.token_expires_at) - utcnow() < _TOKEN_REFRESH_MARGIN
    )
    if needs_login:
        password = decrypt_secret(account.encrypted_cp_password)
        token = await client.login(account.cp_email, password)
        account.cached_access_token = token
        # The platform's own tokens default to a 30-minute lifetime (cf.
        # backend/app/core/config.py access_token_expire_minutes) — this service
        # doesn't query that value, it just assumes the same conservative default
        # and refreshes a few minutes early.
        account.token_expires_at = utcnow() + dt.timedelta(minutes=25)
        await db.flush()
    else:
        client.token = account.cached_access_token
    return client
