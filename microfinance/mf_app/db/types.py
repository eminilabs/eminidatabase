"""Portable column types shared by all models.

GUID stores UUIDs as native UUID on PostgreSQL and CHAR(36) elsewhere, so the
same models run against Postgres (institution databases, control DB in prod) and
SQLite (fast unit tests) without divergent schemas. Identical to
backend/app/db/types.py — duplicated intentionally, these are two separate
deployables (cf. docs/architecture/03 §"deux frontières mTLS" for the same
duplication reasoning applied to identifier validation).
"""

from __future__ import annotations

import uuid

from sqlalchemy import CHAR, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)
