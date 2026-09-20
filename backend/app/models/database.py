from __future__ import annotations

import datetime as dt
import enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.cluster import Cluster
    from app.models.project import Project
    from app.models.region import Region


class IsolationLevel(str, enum.Enum):
    SHARED = "shared"
    DEDICATED = "dedicated"


class DatabaseStatus(str, enum.Enum):
    """Mirrors docs/architecture/02-modele-donnees.md §2.3 exactly. RESUMING has no
    dedicated state in that diagram — a resume in progress uses UPDATING, which
    already models "temporarily busy, will return to RUNNING or fail"."""

    CREATING = "creating"
    RUNNING = "running"
    UPDATING = "updating"
    SUSPENDING = "suspending"
    SUSPENDED = "suspended"
    RESTORING = "restoring"
    MIGRATING = "migrating"
    FAILING = "failing"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class Database(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "databases"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_database_project_name"),)

    project_id: Mapped[str] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False)
    # Chosen by the user at creation time — fixed independently of `cluster_id`,
    # which is only assigned once the Orchestrator has placed the database.
    region_id: Mapped[str] = mapped_column(GUID(), ForeignKey("regions.id"), nullable=False)
    cluster_id: Mapped[str | None] = mapped_column(GUID(), ForeignKey("clusters.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Physical Postgres identifier actually used for CREATE DATABASE/ROLE — globally
    # unique and system-generated, so two tenants can both call their database
    # "production" without colliding once placed on a shared cluster.
    physical_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)

    isolation_level: Mapped[IsolationLevel] = mapped_column(
        Enum(IsolationLevel, native_enum=False, length=20),
        default=IsolationLevel.SHARED,
        nullable=False,
    )
    status: Mapped[DatabaseStatus] = mapped_column(
        Enum(DatabaseStatus, native_enum=False, length=20),
        default=DatabaseStatus.CREATING,
        nullable=False,
    )

    cpu_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    ram_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_limit_gb: Mapped[int] = mapped_column(Integer, nullable=False)

    connection_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connection_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    backup_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship()
    region: Mapped[Region] = relationship()
    cluster: Mapped[Cluster | None] = relationship()
