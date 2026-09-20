from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class UsageMetric(str, enum.Enum):
    CPU_HOURS = "cpu_hours"
    STORAGE_GB_HOURS = "storage_gb_hours"
    CONNECTIONS = "connections"
    # cf. app/scheduler.py::meter_usage docstring — no network egress
    # instrumentation exists anywhere in the agent/proxy layer today, so this
    # metric is never emitted. Kept in the enum (matches the ERD in doc 02)
    # so a future increment that adds real egress counting doesn't need a
    # schema migration, but it stays honestly unbilled until that exists.
    EGRESS_GB = "egress_gb"


class UsageRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """cf. docs/architecture/02 §2.2 — "alimenté par le monitoring, pas par une
    logique ad hoc dans l'API". Written exclusively by app/scheduler.py's
    meter_usage() tick, never by an API endpoint."""

    __tablename__ = "usage_records"

    database_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("databases.id"), nullable=False, index=True
    )
    metric: Mapped[UsageMetric] = mapped_column(
        Enum(UsageMetric, native_enum=False, length=20), nullable=False
    )
    value: Mapped[Numeric] = mapped_column(Numeric(18, 6), nullable=False)
    period_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
