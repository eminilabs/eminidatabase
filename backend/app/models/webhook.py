from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.organization import Organization

# Cf. docs/architecture/07-api-cli-sdk.md §7.4. "database.running" from that list is
# deliberately not separate from "database.created" here — in this platform's flow
# a create job either fails or lands directly on RUNNING, so a second event at the
# same instant would carry no new information.
SUPPORTED_EVENT_TYPES = frozenset(
    {
        "database.created",
        "database.failed",
        "backup.completed",
        "backup.failed",
        "restore.completed",
        "invoice.paid",
    }
)


class Webhook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhooks"

    organization_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("organizations.id"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # HMAC signing key. Encrypted (app.services.secrets), not hashed — unlike a
    # login credential we only ever need to *verify*, delivering a webhook means
    # recomputing HMAC(secret, payload) on every delivery, which needs the actual
    # secret back, not just a one-way check of it.
    encrypted_secret: Mapped[str] = mapped_column(String(500), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization: Mapped[Organization] = relationship()
