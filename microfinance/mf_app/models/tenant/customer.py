from __future__ import annotations

import enum

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.tenant_base import TenantBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, TenantBase):
    __tablename__ = "customers"

    branch_id: Mapped[str] = mapped_column(GUID(), ForeignKey("branches.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    kyc_status: Mapped[KYCStatus] = mapped_column(
        Enum(KYCStatus, native_enum=False, length=20), default=KYCStatus.PENDING, nullable=False
    )
    identity_documents: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
