"""The operational record for a staff member, living in the institution's own
database — distinct from MFStaffUser (control DB), which is the login account.
The two are linked by an opaque id (MFStaffUser.tenant_agent_id), never a FK,
since they live in two separate PostgreSQL databases (cf. docs/architecture/08
§8.6)."""

from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID
from mf_app.models.staff_user import MFStaffRole


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "agents"

    # Nullable: an institution_admin oversees every branch, so isn't tied to one
    # (branch_manager/loan_officer/teller normally are, enforced at the API layer,
    # not by a NOT NULL constraint that would wrongly also apply to admins).
    branch_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("branches.id"), nullable=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[MFStaffRole] = mapped_column(
        Enum(MFStaffRole, native_enum=False, length=30), nullable=False
    )
