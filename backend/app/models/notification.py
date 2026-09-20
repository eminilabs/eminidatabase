from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

# Open vocabulary, not a CHECK-constrained enum: cf. app/services/notification_service.py,
# the single place that knows how to render each of these into a title/body/email.
NOTIFICATION_TYPES = frozenset(
    {
        "welcome",
        "invoice_created",
        "invoice_paid",
        "payment_failed",
        "subscription_changed",
    }
)


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """In-app notification row — the durable half of every notification this
    platform sends (cf. app/services/notification_service.py). The email sent
    alongside it (via Resend) is best-effort and never persisted: if Resend is
    down, the in-app notification still exists, which is why this table is
    written first and unconditionally."""

    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
