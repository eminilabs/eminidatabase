"""Password hashing, JWT issuance/verification, and operator-token helpers.

Kept separate from business logic so every place that touches secrets goes
through one audited module — same convention as backend/app/core/security.py.
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from mf_app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True)
class StaffTokenPayload:
    staff_user_id: uuid.UUID
    institution_id: uuid.UUID
    role: str


def create_staff_access_token(
    *, staff_user_id: uuid.UUID, institution_id: uuid.UUID, role: str
) -> str:
    settings = get_settings()
    expire = dt.datetime.now(dt.UTC) + dt.timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(staff_user_id),
        "institution_id": str(institution_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_staff_access_token(token: str) -> StaffTokenPayload | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    try:
        return StaffTokenPayload(
            staff_user_id=uuid.UUID(payload["sub"]),
            institution_id=uuid.UUID(payload["institution_id"]),
            role=payload["role"],
        )
    except (KeyError, ValueError):
        return None


def generate_random_password(length: int = 24) -> str:
    return secrets.token_urlsafe(length)


def verify_operator_token(token: str) -> bool:
    """Constant-time-safe verification (argon2 verify) of the shared operator
    bearer token gating institution onboarding (cf. §8.11 — not per-user, a single
    shared internal secret, same tier of simplicity as the platform's own node
    bootstrap tokens)."""
    settings = get_settings()
    if not settings.mf_operator_token_hash:
        return False
    try:
        return _hasher.verify(settings.mf_operator_token_hash, token)
    except VerifyMismatchError:
        return False


def generate_operator_token() -> tuple[str, str]:
    """Returns (token, hash). The token is shown once, at generation time."""
    token = secrets.token_urlsafe(32)
    return token, _hasher.hash(token)
