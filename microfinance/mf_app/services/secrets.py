"""Application-level encryption for secrets at rest (the platform account's CP
token, each institution's database password) — same Fernet envelope scheme as
backend/app/services/secrets.py, a separate key for a separate deployable."""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from mf_app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().secret_encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
