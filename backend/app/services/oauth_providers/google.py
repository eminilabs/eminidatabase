"""Google OAuth2 / OpenID Connect — raw REST via httpx, no `google-auth`/
`google-auth-oauthlib` dependency: it's three well-documented HTTP calls, the
same "no SDK, httpx everywhere" convention as every other external integration
in this codebase (NOWPayments, FedaPay, Resend).
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthError(RuntimeError):
    pass


def _redirect_uri() -> str:
    return f"{get_settings().oauth_redirect_base_url}/api/v1/auth/oauth/google/callback"


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Returns the access token."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _redirect_uri(),
            },
        )
    if resp.status_code >= 400:
        raise GoogleOAuthError(
            f"Google token exchange failed: {resp.status_code} {resp.text[:500]}"
        )
    return resp.json()["access_token"]


async def fetch_user_info(access_token: str) -> dict:
    """Returns {"provider_account_id", "email", "email_verified"}."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
    if resp.status_code >= 400:
        raise GoogleOAuthError(f"Google userinfo failed: {resp.status_code} {resp.text[:500]}")
    body = resp.json()
    return {
        "provider_account_id": body["sub"],
        "email": body.get("email"),
        # Google returns this as an actual bool (unlike GitHub's per-email list).
        "email_verified": bool(body.get("email_verified", False)),
    }
