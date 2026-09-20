"""GitHub OAuth2 — raw REST via httpx, same convention as google.py. GitHub's
`/user` endpoint often returns `email: null` when the user's email is private,
so the verified primary email has to come from `/user/emails` instead.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_EMAILS_URL = "https://api.github.com/user/emails"


class GitHubOAuthError(RuntimeError):
    pass


def _redirect_uri() -> str:
    return f"{get_settings().oauth_redirect_base_url}/api/v1/auth/oauth/github/callback"


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": _redirect_uri(),
        "scope": "read:user user:email",
        "state": state,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Returns the access token."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": _redirect_uri(),
            },
        )
    if resp.status_code >= 400:
        raise GitHubOAuthError(
            f"GitHub token exchange failed: {resp.status_code} {resp.text[:500]}"
        )
    body = resp.json()
    if "error" in body:
        raise GitHubOAuthError(f"GitHub token exchange failed: {body}")
    return body["access_token"]


async def fetch_user_info(access_token: str) -> dict:
    """Returns {"provider_account_id", "email", "email_verified"}."""
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=15) as client:
        user_resp = await client.get(_USER_URL, headers=headers)
        emails_resp = await client.get(_EMAILS_URL, headers=headers)
    if user_resp.status_code >= 400:
        raise GitHubOAuthError(
            f"GitHub user fetch failed: {user_resp.status_code} {user_resp.text[:500]}"
        )
    if emails_resp.status_code >= 400:
        raise GitHubOAuthError(
            f"GitHub emails fetch failed: {emails_resp.status_code} {emails_resp.text[:500]}"
        )

    user = user_resp.json()
    emails = emails_resp.json()
    primary = next((e for e in emails if e.get("primary")), None)
    return {
        "provider_account_id": str(user["id"]),
        "email": primary["email"] if primary else user.get("email"),
        "email_verified": bool(primary["verified"]) if primary else False,
    }
