"""cf. docs/architecture/02-modele-donnees.md (PLANS) and 08 §8.12 — pricing and
quotas are data, never hardcoded Python constants, so changing a price or a
quota never requires a deploy."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    # e.g. {"max_databases": 3, "max_storage_gb": 20, "max_cpu_total": 4} —
    # enforced by app/services/quotas.py at database creation, cf. 03's flow
    # diagram "Quota du plan OK?" gate.
    quotas: Mapped[dict] = mapped_column(JSON, nullable=False)
    # e.g. {"base_fee": "0", "cpu_hour": "0.02", "storage_gb_hour": "0.0005"} —
    # keys match UsageRecord.metric plus "base_fee"; values are decimal strings
    # (never float — cf. app/services/billing.py which parses them as Decimal).
    pricing: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
