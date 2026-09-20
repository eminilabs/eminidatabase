"""Single-row configuration table living inside an institution's own database
(cf. docs/architecture/08 §8.6). Intentionally one row per database — isolation
is by database, not by an institution_id column, so this table never needs one.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin


class InstitutionProfile(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "institution_profile"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="XOF", nullable=False)
