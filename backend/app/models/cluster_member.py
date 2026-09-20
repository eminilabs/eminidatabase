from __future__ import annotations

import datetime as dt
import enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.cluster import Cluster
    from app.models.node import Node


class ClusterMemberRole(str, enum.Enum):
    PRIMARY = "primary"
    REPLICA = "replica"


class ClusterMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cluster_members"

    cluster_id: Mapped[str] = mapped_column(GUID(), ForeignKey("clusters.id"), nullable=False)
    node_id: Mapped[str] = mapped_column(GUID(), ForeignKey("nodes.id"), nullable=False)
    role: Mapped[ClusterMemberRole] = mapped_column(
        Enum(ClusterMemberRole, native_enum=False, length=20),
        default=ClusterMemberRole.PRIMARY,
        nullable=False,
    )
    replication_lag_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promoted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    cluster: Mapped[Cluster] = relationship(back_populates="members")
    node: Mapped[Node] = relationship()
