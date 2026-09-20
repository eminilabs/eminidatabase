from __future__ import annotations

import datetime as dt
import enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.database import Database


class BackupType(str, enum.Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class BackupStatus(str, enum.Enum):
    """Cf. docs/architecture/05-backup-ha-scaling.md §5.1 — a backup being
    COMPLETED does not by itself mean it's trustworthy; VERIFIED does."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    PURGED = "purged"


class Backup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "backups"

    database_id: Mapped[str] = mapped_column(GUID(), ForeignKey("databases.id"), nullable=False)
    type: Mapped[BackupType] = mapped_column(
        Enum(BackupType, native_enum=False, length=20), nullable=False
    )
    status: Mapped[BackupStatus] = mapped_column(
        Enum(BackupStatus, native_enum=False, length=20),
        default=BackupStatus.PENDING,
        nullable=False,
    )
    # Object storage key — the encrypted dump itself lives only in object storage,
    # never on the same disk as the primary database (cahier des charges §21).
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    verification_detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    database: Mapped[Database] = relationship()
