"""OAuth sign-up/sign-in (Google, GitHub) — cf. app/services/oauth_service.py.
Network calls to the providers are monkeypatched at the `oauth_providers`
module boundary, the same pattern test_payments_notifications.py uses for
`payment_providers`. The callback is a full-page browser navigation coming back
from the provider, not a fetch call a frontend script made — it always redirects
to the frontend, carrying the token in a URL fragment on success (`#access_token=`,
never sent to any server) or an `?error=` query param on failure, never a bare
4xx (cf. docs/architecture/04-securite-et-isolation.md §4.8).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pyotp
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.services import oauth_service
from app.services.oauth_providers import github, google
from tests.conftest import TestSessionLocal, register_and_login


def _access_token_from_redirect(location: str) -> str:
    assert location.startswith(f"{get_settings().frontend_oauth_redirect_url}/auth/callback#")
    fragment = urlsplit(location).fragment
    return parse_qs(fragment)["access_token"][0]


def _error_from_redirect(location: str) -> str:
    assert location.startswith(f"{get_settings().frontend_oauth_redirect_url}/auth/callback?")
    query = urlsplit(location).query
    return parse_qs(query)["error"][0]


async def test_oauth_login_redirects_to_provider_consent_screen(client: AsyncClient):
    resp = await client.get("/api/v1/auth/oauth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307), resp.text
    assert "accounts.google.com" in resp.headers["location"]

    resp = await client.get("/api/v1/auth/oauth/github/login", follow_redirects=False)
    assert resp.status_code in (302, 307), resp.text
    assert "github.com/login/oauth/authorize" in resp.headers["location"]


async def test_oauth_login_unknown_provider_rejected(client: AsyncClient):
    resp = await client.get("/api/v1/auth/oauth/facebook/login", follow_redirects=False)
    assert resp.status_code == 404


async def test_google_callback_creates_new_user(client: AsyncClient, monkeypatch):
    async def _fake_exchange_code(code):
        assert code == "auth-code-1"
        return "access-token-1"

    async def _fake_fetch_user_info(access_token):
        return {
            "provider_account_id": "g-123",
            "email": "newgoogle@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(google, "exchange_code", _fake_exchange_code)
    monkeypatch.setattr(google, "fetch_user_info", _fake_fetch_user_info)

    state = oauth_service._create_state("google")
    resp = await client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "auth-code-1", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    access_token = _access_token_from_redirect(resp.headers["location"])

    async with TestSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == "newgoogle@example.com"))
        ).scalar_one()
        assert user.password_hash is None
        link = (
            await db.execute(select(OAuthAccount).where(OAuthAccount.user_id == user.id))
        ).scalar_one()
        assert link.provider_account_id == "g-123"

    notif_resp = await client.get(
        "/api/v1/notifications", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert any(n["type"] == "welcome" for n in notif_resp.json())


async def test_github_callback_links_existing_password_account_by_email(
    client: AsyncClient, monkeypatch
):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "hybrid@example.com", "password": "correct-horse-battery"},
    )

    async def _fake_exchange_code(code):
        return "gh-access-token"

    async def _fake_fetch_user_info(access_token):
        return {
            "provider_account_id": "gh-456",
            "email": "hybrid@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(github, "exchange_code", _fake_exchange_code)
    monkeypatch.setattr(github, "fetch_user_info", _fake_fetch_user_info)

    state = oauth_service._create_state("github")
    resp = await client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"code": "gh-code", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    _access_token_from_redirect(resp.headers["location"])  # asserts the success shape.

    async with TestSessionLocal() as db:
        users = (
            (await db.execute(select(User).where(User.email == "hybrid@example.com")))
            .scalars()
            .all()
        )
        assert len(users) == 1  # linked to the existing account, not duplicated.
        assert users[0].password_hash is not None  # the original password is untouched.


async def test_oauth_callback_rejects_unverified_email(client: AsyncClient, monkeypatch):
    async def _fake_exchange_code(code):
        return "tok"

    async def _fake_fetch_user_info(access_token):
        return {
            "provider_account_id": "g-789",
            "email": "unverified@example.com",
            "email_verified": False,
        }

    monkeypatch.setattr(google, "exchange_code", _fake_exchange_code)
    monkeypatch.setattr(google, "fetch_user_info", _fake_fetch_user_info)

    state = oauth_service._create_state("google")
    resp = await client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    assert "verified email" in _error_from_redirect(resp.headers["location"])


async def test_oauth_callback_rejects_tampered_state(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "c", "state": "not-a-real-token"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    _error_from_redirect(resp.headers["location"])


async def test_oauth_callback_rejects_state_from_a_different_provider(client: AsyncClient):
    state_for_github = oauth_service._create_state("github")
    resp = await client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "c", "state": state_for_github},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    _error_from_redirect(resp.headers["location"])


async def test_oauth_callback_blocked_when_mfa_enabled(client: AsyncClient, monkeypatch):
    headers = await register_and_login(client, "mfaguard@example.com")
    enable_resp = await client.post("/api/v1/auth/mfa/enable", headers=headers)
    uri = enable_resp.json()["provisioning_uri"]
    secret = dict(part.split("=") for part in uri.split("?")[1].split("&"))["secret"]
    await client.post(
        "/api/v1/auth/mfa/verify", json={"otp_code": pyotp.TOTP(secret).now()}, headers=headers
    )

    async def _fake_exchange_code(code):
        return "tok"

    async def _fake_fetch_user_info(access_token):
        return {
            "provider_account_id": "g-mfa",
            "email": "mfaguard@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(google, "exchange_code", _fake_exchange_code)
    monkeypatch.setattr(google, "fetch_user_info", _fake_fetch_user_info)

    state = oauth_service._create_state("google")
    resp = await client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    assert "MFA is enabled" in _error_from_redirect(resp.headers["location"])


async def test_repeated_oauth_login_reuses_the_same_link(client: AsyncClient, monkeypatch):
    async def _fake_exchange_code(code):
        return "tok"

    async def _fake_fetch_user_info(access_token):
        return {
            "provider_account_id": "g-repeat",
            "email": "repeat@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(google, "exchange_code", _fake_exchange_code)
    monkeypatch.setattr(google, "fetch_user_info", _fake_fetch_user_info)

    for _ in range(2):
        state = oauth_service._create_state("google")
        resp = await client.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307), resp.text
        _access_token_from_redirect(resp.headers["location"])

    async with TestSessionLocal() as db:
        users = (
            (await db.execute(select(User).where(User.email == "repeat@example.com")))
            .scalars()
            .all()
        )
        assert len(users) == 1
        links = (
            (await db.execute(select(OAuthAccount).where(OAuthAccount.user_id == users[0].id)))
            .scalars()
            .all()
        )
        assert len(links) == 1
