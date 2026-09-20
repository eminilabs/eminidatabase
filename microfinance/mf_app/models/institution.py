"""An institution = a project + database provisioned on the Control Plane, one
per microfinance customer (cf. docs/architecture/08 §8.3-8.4). This row is the
ONLY place the mapping between an institution and its platform resources lives —
never duplicated, never re-derived."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.control_base import ControlBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class MFInstitutionStatus(str, enum.Enum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"
    SUSPENDED = "suspended"


class MFInstitution(UUIDPrimaryKeyMixin, TimestampMixin, ControlBase):
    __tablename__ = "mf_institutions"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False, index=True)
    status: Mapped[MFInstitutionStatus] = mapped_column(
        Enum(MFInstitutionStatus, native_enum=False, length=20),
        default=MFInstitutionStatus.PROVISIONING,
        nullable=False,
    )

    # Platform resource mapping (cf. §8.3 — one project+database per institution,
    # inside the single MFPlatformAccount's organization).
    cp_project_id: Mapped[str | None] = mapped_column(GUID(), nullable=True)
    cp_database_id: Mapped[str | None] = mapped_column(GUID(), nullable=True)

    # Connection to the institution's own provisioned database — fetched once via
    # the SDK's get_connection() at onboarding time and cached here (Fernet
    # encrypted password, same scheme as everywhere else in this codebase).
    db_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    db_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    encrypted_db_password: Mapped[str | None] = mapped_column(String(500), nullable=True)

    failure_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
