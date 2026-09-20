from __future__ import annotations

import datetime as dt
import enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.region import Region


class NodeStatus(str, enum.Enum):
    """Operator-declared status. Staleness-based 'offline' is computed at read time,
    never stored here, so a heartbeat resuming doesn't require an operator action."""

    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    DRAINING = "draining"


class Node(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nodes"

    region_id: Mapped[str] = mapped_column(GUID(), ForeignKey("regions.id"), nullable=False)

    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    cpu_total: Mapped[int] = mapped_column(Integer, nullable=False)
    ram_total_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_total_gb: Mapped[int] = mapped_column(Integer, nullable=False)

    cpu_used: Mapped[float | None] = mapped_column(nullable=True)
    ram_used_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_used_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    agent_port: Mapped[int] = mapped_column(Integer, nullable=False, default=9443)
    postgres_port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)

    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus, native_enum=False, length=20), default=NodeStatus.ACTIVE, nullable=False
    )

    node_secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    certificate_serial: Mapped[str | None] = mapped_column(String(64), nullable=True)

    last_heartbeat_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    region: Mapped[Region] = relationship(back_populates="nodes")
