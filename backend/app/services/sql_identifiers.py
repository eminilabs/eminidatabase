"""Identifier validation shared by anything that names a Postgres object.

cf. docs/architecture/03 §"Construction sécurisée des commandes SQL" — every name
that ends up in a DDL statement is checked against this pattern *before* it is used,
on both sides of the mTLS boundary (Control Plane here, and independently again in
agent/app/postgres_admin.py — intentional defense in depth, not shared code, since
the two are separate deployables).
"""

from __future__ import annotations

import re

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")


def is_valid_identifier(name: str) -> bool:
    return bool(_IDENTIFIER_RE.match(name))


def validate_identifier(name: str) -> str:
    if not is_valid_identifier(name):
        raise ValueError(
            f"Invalid identifier {name!r}: must be lowercase, start with a letter, "
            "3-63 chars, [a-z0-9_] only"
        )
    return name
