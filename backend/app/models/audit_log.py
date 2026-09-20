from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only audit trail. Never updated or deleted by application code."""

    __tablename__ = "audit_logs"

    organization_id: Mapped[str | None] = mapped_column(
        GUID(), ForeignKey("organizations.id"), nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(GUID(), nullable=True)

    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
