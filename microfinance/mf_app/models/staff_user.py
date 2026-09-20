"""Institution staff accounts — distinct from the Control Plane's own USERS
(cf. docs/architecture/08 §8.4/§8.9). A staff account belongs to exactly one
institution; there is no cross-institution account, unlike a CP User which can
belong to several organizations."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.control_base import ControlBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class MFStaffRole(str, enum.Enum):
    INSTITUTION_ADMIN = "institution_admin"
    BRANCH_MANAGER = "branch_manager"
    LOAN_OFFICER = "loan_officer"
    TELLER = "teller"


class MFStaffUser(UUIDPrimaryKeyMixin, TimestampMixin, ControlBase):
    __tablename__ = "mf_staff_users"

    institution_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("mf_institutions.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[MFStaffRole] = mapped_column(
        Enum(MFStaffRole, native_enum=False, length=30), nullable=False
    )
    # Opaque link to the tenant-DB Agent row this staff account operates as
    # (cf. §8.6 — two separate PostgreSQL databases, no FK possible across them).
    tenant_agent_id: Mapped[str | None] = mapped_column(GUID(), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("institution_id", "email", name="uq_mf_staff_institution_email"),
    )
