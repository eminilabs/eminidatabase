"""Declarative base for the per-institution TENANT schema (branches, agents,
customers, accounts, loans, ledger — cf. docs/architecture/08 §8.6). Every table
here is created inside an institution's own provisioned database (via
alembic_tenant/), never in this service's Control DB. Separate Base/metadata from
control_base.py — see that module's docstring for why."""

import datetime as dt
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from mf_app.db.types import GUID


class TenantBase(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
