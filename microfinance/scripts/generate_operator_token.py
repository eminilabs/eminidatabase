"""Generates the shared operator bearer token gating institution onboarding
(cf. docs/architecture/08 §8.11). Prints the TOKEN (give it to whoever calls
POST /institutions) and the HASH (put it in MF_OPERATOR_TOKEN_HASH) — the hash
is what gets persisted, never the plaintext token.

Usage:
    python -m scripts.generate_operator_token
"""

from __future__ import annotations

from mf_app.core.security import generate_operator_token

if __name__ == "__main__":
    token, token_hash = generate_operator_token()
    print(f"TOKEN (give to the operator): {token}")
    print(f"HASH  (put in MF_OPERATOR_TOKEN_HASH): {token_hash}")
