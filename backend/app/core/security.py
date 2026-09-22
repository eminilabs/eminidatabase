"""Password hashing, JWT issuance/verification, and TOTP (MFA) helpers.

Kept separate from business logic so every place that touches secrets goes
through one audited module (cf. docs/architecture/04-securite-et-isolation.md).
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    token_version: int


def create_access_token(user_id: uuid.UUID, token_version: int) -> str:
    settings = get_settings()
    expire = dt.datetime.now(dt.UTC) + dt.timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "ver": token_version, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload | None:
    """Returns None for any malformed/expired/mis-signed token — callers don't
    distinguish why, just that the caller must re-authenticate. `ver` is
    checked against the user's current `token_version` by the caller (cf.
    app/core/dependencies.py), not here — that needs a DB lookup this
    function deliberately doesn't do, so a revoked token still decodes fine,
    it just won't match."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    ver = payload.get("ver")
    user_id_raw = payload.get("sub")
    if user_id_raw is None or ver is None:
        return None
    try:
        return TokenPayload(user_id=uuid.UUID(user_id_raw), token_version=int(ver))
    except (ValueError, TypeError):
        return None


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def mfa_provisioning_uri(secret: str, email: str, issuer: str = "eminidatabase") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, hash). Only the hash is persisted."""
    prefix = secrets.token_hex(4)
    secret_part = secrets.token_urlsafe(32)
    full_key = f"edb_{prefix}_{secret_part}"
    return full_key, prefix, hash_api_key(full_key)


def hash_api_key(full_key: str) -> str:
    return _hasher.hash(full_key)


def verify_api_key(full_key: str, key_hash: str) -> bool:
    try:
        return _hasher.verify(key_hash, full_key)
    except VerifyMismatchError:
        return False


_API_KEY_PREFIX_LEN = 8  # secrets.token_hex(4) above


def extract_api_key_prefix(full_key: str) -> str | None:
    """Pulls the lookup prefix out of an `edb_<prefix>_<secret>` key, without
    needing to split on `_` — `token_urlsafe`'s alphabet can itself contain
    `_`, so a naive split would break. Returns None if the string isn't
    shaped like one of our keys at all (so callers can fall back to treating
    it as a JWT instead of guessing)."""
    header = "edb_"
    if not full_key.startswith(header):
        return None
    rest = full_key[len(header) :]
    prefix, sep, secret_part = rest.partition("_")
    if len(prefix) != _API_KEY_PREFIX_LEN or sep != "_" or not secret_part:
        return None
    return prefix


def generate_random_password(length: int = 24) -> str:
    return secrets.token_urlsafe(length)


def generate_node_secret() -> tuple[str, str]:
    """Returns (secret, hash). The secret is shown to the agent once, at
    registration, and never persisted in plaintext (cf. Règle 15)."""
    secret = secrets.token_urlsafe(48)
    return secret, _hasher.hash(secret)


def verify_node_secret(secret: str, secret_hash: str) -> bool:
    try:
        return _hasher.verify(secret_hash, secret)
    except VerifyMismatchError:
        return False


def generate_bootstrap_token() -> tuple[str, str]:
    """Returns (token, hash) for a one-shot node registration token."""
    token = secrets.token_urlsafe(32)
    return token, _hasher.hash(token)


def verify_bootstrap_token(token: str, token_hash: str) -> bool:
    try:
        return _hasher.verify(token_hash, token)
    except VerifyMismatchError:
        return False
