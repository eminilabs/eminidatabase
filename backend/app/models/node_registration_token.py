from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.region import Region


class NodeRegistrationToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One-shot bootstrap token an operator hands to a new VPS so its agent can
    register itself. Never reusable — cf. docs/architecture/03 §3.2 bootstrap flow."""

    __tablename__ = "node_registration_tokens"

    region_id: Mapped[str] = mapped_column(GUID(), ForeignKey("regions.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    region: Mapped[Region] = relationship()
