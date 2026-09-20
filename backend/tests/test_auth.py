import pyotp
from httpx import AsyncClient

from tests.conftest import register_and_login


async def test_register_creates_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_duplicate_email_rejected(client: AsyncClient):
    payload = {"email": "bob@example.com", "password": "correct-horse-battery"}
    first = await client.post("/api/v1/auth/register", json=payload)
    second = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


async def test_login_with_correct_password_returns_token(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "correct-horse-battery"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_with_wrong_password_rejected(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "correct-horse-battery"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "dave@example.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401


async def test_me_requires_bearer_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(client: AsyncClient):
    headers = await register_and_login(client, "erin@example.com")
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "erin@example.com"


async def test_mfa_enable_then_login_requires_otp(client: AsyncClient):
    headers = await register_and_login(client, "frank@example.com")

    enable_resp = await client.post("/api/v1/auth/mfa/enable", headers=headers)
    assert enable_resp.status_code == 200
    uri = enable_resp.json()["provisioning_uri"]
    secret = dict(part.split("=") for part in uri.split("?")[1].split("&"))["secret"]

    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/auth/mfa/verify", json={"otp_code": code}, headers=headers
    )
    assert verify_resp.status_code == 204

    # Password alone is no longer enough once MFA is enabled.
    login_no_otp = await client.post(
        "/api/v1/auth/login",
        json={"email": "frank@example.com", "password": "correct-horse-battery"},
    )
    assert login_no_otp.status_code == 401

    fresh_code = pyotp.TOTP(secret).now()
    login_with_otp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "frank@example.com",
            "password": "correct-horse-battery",
            "otp_code": fresh_code,
        },
    )
    assert login_with_otp.status_code == 200
