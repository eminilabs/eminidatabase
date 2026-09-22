from __future__ import annotations

import datetime as dt
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.core.security import (
    create_access_token,
    generate_mfa_secret,
    hash_password,
    mfa_provisioning_uri,
    verify_password,
    verify_totp_code,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    MeResponse,
    MfaEnableResponse,
    MfaVerifyRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
)
from app.services import oauth_service
from app.services.audit import record_audit
from app.services.notification_service import notify_welcome

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MeResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    await db.flush()
    await record_audit(
        db, action="USER_REGISTERED", resource_type="user", resource_id=user.id, user_id=user.id
    )
    await notify_welcome(db, user)
    await db.commit()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
    )
    if (
        user is None
        or user.password_hash is None
        or not verify_password(payload.password, user.password_hash)
    ):
        await record_audit(
            db,
            action="LOGIN_FAILED",
            resource_type="user",
            ip_address=request.client.host if request.client else None,
            result="failure",
        )
        await db.commit()
        raise invalid_credentials

    if user.mfa_enabled:
        if not payload.otp_code or not verify_totp_code(user.mfa_secret, payload.otp_code):
            await record_audit(
                db,
                action="LOGIN_MFA_FAILED",
                resource_type="user",
                resource_id=user.id,
                user_id=user.id,
                result="failure",
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid OTP code"
            )

    user.last_login_at = dt.datetime.now(dt.UTC)
    await record_audit(
        db,
        action="LOGIN_SUCCEEDED",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return TokenResponse(access_token=create_access_token(user.id, user.token_version))


@router.get("/oauth/{provider}/login", response_model=None)
async def oauth_login(provider: str) -> RedirectResponse:
    """Redirects the browser to Google/GitHub's consent screen."""
    return oauth_service.build_authorize_redirect(provider)


@router.get("/oauth/{provider}/callback", response_model=None)
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Hands the outcome off to the frontend rather than returning JSON — this is
    a real browser navigation coming back from Google/GitHub, not an API call a
    frontend script made itself. On success the token travels in a URL
    *fragment* (`#access_token=...`), which browsers never send to any server
    (not logged here, not visible to the frontend's own server-side rendering) —
    only the client-side JS that reads `window.location.hash` on
    frontend/app/auth/callback ever sees it. Failures carry a `?error=` query
    param instead, since there's no token to protect in that case."""
    frontend_base = get_settings().frontend_oauth_redirect_url

    try:
        user = await oauth_service.handle_callback(db, provider, code, state)
    except oauth_service.OAuthLoginError as exc:
        await db.rollback()
        return RedirectResponse(f"{frontend_base}/auth/callback?error={quote(str(exc))}")

    if user.mfa_enabled:
        # This account's second factor is our own TOTP, which Google/GitHub have
        # no notion of — an OAuth login alone cannot satisfy it. Documented gap,
        # not a silent bypass: closing it properly needs the frontend to host a
        # second "enter your OTP code" step, which frontend/app/auth/callback
        # does not implement yet — for now the user is pointed back at
        # password+OTP login instead.
        await db.rollback()
        message = "MFA is enabled on this account — sign in with your password and OTP code instead"
        return RedirectResponse(f"{frontend_base}/auth/callback?error={quote(message)}")

    user.last_login_at = dt.datetime.now(dt.UTC)
    await record_audit(
        db,
        action="LOGIN_SUCCEEDED",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    token = create_access_token(user.id, user.token_version)
    return RedirectResponse(f"{frontend_base}/auth/callback#access_token={token}")


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_all_sessions(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    """Invalidates every JWT issued to this user so far, including the one
    used to call this endpoint — every previously issued token carries the
    `token_version` it was signed with (cf. app/core/security.py), and
    get_current_user rejects any token whose version no longer matches the
    user's current one. No per-session table to track: "sign out everywhere"
    is just this one increment. Does not touch API keys, which are revoked
    individually and don't carry a token_version at all."""
    current_user.token_version += 1
    await record_audit(
        db,
        action="ALL_SESSIONS_REVOKED",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id,
    )
    await db.commit()


@router.post("/mfa/enable", response_model=MfaEnableResponse)
async def enable_mfa(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MfaEnableResponse:
    secret = generate_mfa_secret()
    current_user.mfa_secret = secret
    await db.commit()
    return MfaEnableResponse(
        provisioning_uri=mfa_provisioning_uri(secret, current_user.email)
    )


@router.post("/mfa/verify", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def verify_mfa(
    payload: MfaVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not current_user.mfa_secret or not verify_totp_code(
        current_user.mfa_secret, payload.otp_code
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP code")
    current_user.mfa_enabled = True
    await record_audit(
        db,
        action="MFA_ENABLED",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id,
    )
    await db.commit()
