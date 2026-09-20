"""Google/GitHub OAuth2 sign-up and sign-in — cf. app/services/oauth_providers/
{google,github}.py for the provider-specific HTTP calls. This module owns the
CSRF `state` token, the account linking/creation logic, and the (still open)
MFA interaction gap.

The `state` parameter is a short-lived, signed JWT (same secret/algorithm as
session tokens, distinct `purpose` claim) rather than server-side session
storage — this API has no session store, and a stateless signed token is the
same trick already used for access tokens themselves. It only has to survive
the round trip to the provider's consent screen and back.
"""

from __future__ import annotations

import datetime as dt

import jwt
from fastapi import HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.oauth_account import OAuthAccount, OAuthProviderName
from app.models.user import User
from app.services.audit import record_audit
from app.services.notification_service import notify_welcome
from app.services.oauth_providers import github, google

_STATE_TTL_SECONDS = 600  # generous enough for a user to click through a consent screen.

_PROVIDERS = {
    OAuthProviderName.GOOGLE.value: google,
    OAuthProviderName.GITHUB.value: github,
}


class OAuthLoginError(Exception):
    pass


def _get_provider_module(provider: str):
    module = _PROVIDERS.get(provider)
    if module is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Unknown OAuth provider: {provider!r}"
        )
    return module


def _create_state(provider: str) -> str:
    settings = get_settings()
    payload = {
        "purpose": "oauth_state",
        "provider": provider,
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(seconds=_STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _verify_state(state: str, provider: str) -> None:
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise OAuthLoginError("Invalid or expired OAuth state") from exc
    if payload.get("purpose") != "oauth_state" or payload.get("provider") != provider:
        raise OAuthLoginError("Invalid OAuth state")


def build_authorize_redirect(provider: str) -> RedirectResponse:
    module = _get_provider_module(provider)
    state = _create_state(provider)
    return RedirectResponse(module.build_authorize_url(state))


async def handle_callback(db: AsyncSession, provider: str, code: str, state: str) -> User:
    module = _get_provider_module(provider)
    _verify_state(state, provider)

    try:
        access_token = await module.exchange_code(code)
        info = await module.fetch_user_info(access_token)
    except Exception as exc:  # noqa: BLE001 — any provider-side failure is a login failure, not a 500.
        raise OAuthLoginError(f"{provider} authentication failed: {exc}") from exc

    if not info.get("email_verified") or not info.get("email"):
        # Never create/link an account off an email the provider itself hasn't
        # verified — that would let anyone claim an existing user's account by
        # registering an OAuth app with a matching, unverified email.
        raise OAuthLoginError(f"{provider} did not return a verified email address")

    provider_enum = OAuthProviderName(provider)
    provider_account_id = info["provider_account_id"]
    email = info["email"]

    existing_link = (
        await db.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider_enum,
                OAuthAccount.provider_account_id == provider_account_id,
            )
        )
    ).scalar_one_or_none()
    if existing_link is not None:
        user = await db.get(User, existing_link.user_id)
        return user

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    is_new_user = user is None
    if user is None:
        user = User(email=email, password_hash=None)
        db.add(user)
        await db.flush()

    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=provider_enum,
            provider_account_id=provider_account_id,
            email=email,
        )
    )
    await db.flush()

    if is_new_user:
        await record_audit(
            db, action="USER_REGISTERED", resource_type="user", resource_id=user.id, user_id=user.id
        )
        await notify_welcome(db, user)

    return user
