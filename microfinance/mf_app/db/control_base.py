"""Declarative base for the service's own Control DB (MFPlatformAccount,
MFInstitution, MFStaffUser, MFJob) — metadata only, never institution business
data. Kept as a separate Base/metadata from tenant_base.py so the two Alembic
setups (alembic_control/, alembic_tenant/) never accidentally pick up each
other's tables (cf. docs/architecture/08 §8.5)."""

import datetime as dt
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from mf_app.db.types import GUID


class ControlBase(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
