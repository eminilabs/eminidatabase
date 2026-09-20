from __future__ import annotations

import datetime as dt
import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.database import Database


class CredentialScope(str, enum.Enum):
    APP = "app"
    READONLY = "readonly"
    ADMIN = "admin"


class DatabaseCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "database_credentials"

    database_id: Mapped[str] = mapped_column(GUID(), ForeignKey("databases.id"), nullable=False)
    # Physical Postgres role name — always system-generated (cf. Database.physical_name
    # for the same reasoning): role names are unique cluster-wide, so a user-chosen
    # name could collide with another tenant's role on a shared cluster.
    role_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    # User-facing label for additional roles (Phase 4+); null for the original
    # provisioning-time owner credential, which has no user-chosen name.
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # True only for the credential created at provisioning time (app/services/
    # orchestrator.py). Deletion protection is keyed off this, not `scope` — a
    # user can create further APP-scope roles, and none of those should be
    # confused with the one the database can't function without.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Encrypted with app.services.secrets — never plaintext (Règle 15).
    encrypted_password: Mapped[str] = mapped_column(String(500), nullable=False)
    scope: Mapped[CredentialScope] = mapped_column(
        Enum(CredentialScope, native_enum=False, length=20),
        default=CredentialScope.APP,
        nullable=False,
    )
    rotated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    database: Mapped[Database] = relationship()
