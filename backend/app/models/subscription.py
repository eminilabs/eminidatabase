from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One per organization (cf. docs/architecture/02 ERD — created automatically
    on the default/free plan when the organization itself is created, so every
    organization always has exactly one, never a nullable relationship to check
    everywhere else)."""

    __tablename__ = "subscriptions"

    organization_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("organizations.id"), unique=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(GUID(), ForeignKey("plans.id"), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False, length=20),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
    )
    current_period_start: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
