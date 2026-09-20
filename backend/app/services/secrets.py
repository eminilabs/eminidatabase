"""Application-level encryption for database credentials at rest.

cf. docs/architecture/04-securite-et-isolation.md §4.4 — Vault is the target; this
Fernet-based envelope is the documented "chiffrement applicatif" interim, keyed by
`SECRET_ENCRYPTION_KEY` (never the code, never the database).
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().secret_encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
