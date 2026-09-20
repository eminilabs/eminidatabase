from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.cluster_member import ClusterMember
    from app.models.region import Region


class ClusterTopology(str, enum.Enum):
    SINGLE = "single"
    PRIMARY_REPLICA = "primary_replica"


class ClusterStatus(str, enum.Enum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    DEGRADED = "degraded"
    DELETED = "deleted"


class Cluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clusters"

    region_id: Mapped[str] = mapped_column(GUID(), ForeignKey("regions.id"), nullable=False)
    topology: Mapped[ClusterTopology] = mapped_column(
        Enum(ClusterTopology, native_enum=False, length=20),
        default=ClusterTopology.SINGLE,
        nullable=False,
    )
    # A shared cluster may host several tenants' Databases; a non-shared one is
    # dedicated to exactly one Database (cf. docs/architecture §13).
    shared: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    postgres_version: Mapped[str] = mapped_column(String(20), default="16", nullable=False)
    status: Mapped[ClusterStatus] = mapped_column(
        Enum(ClusterStatus, native_enum=False, length=20),
        default=ClusterStatus.PROVISIONING,
        nullable=False,
    )

    region: Mapped[Region] = relationship()
    members: Mapped[list[ClusterMember]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )
