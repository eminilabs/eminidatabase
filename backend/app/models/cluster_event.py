from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class ClusterEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Incident trail for cluster-level operations (failover, replica changes) —
    cahier des charges: every failover must be an auditable, documented incident,
    not a silent state change."""

    __tablename__ = "cluster_events"

    cluster_id: Mapped[str] = mapped_column(GUID(), ForeignKey("clusters.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
