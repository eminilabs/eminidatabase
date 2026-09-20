"""Timezone helpers.

SQLite (used in tests) does not round-trip tzinfo the way Postgres does, so any
datetime read back from the DB needs normalizing before comparison against a
freshly created aware datetime — otherwise the same code behaves differently on
SQLite vs. Postgres.
"""

from __future__ import annotations

import datetime as dt


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def as_aware_utc(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)
