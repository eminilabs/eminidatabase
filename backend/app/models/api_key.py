from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"

    organization_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("organizations.id"), nullable=False
    )
    # The user who created this key — a request authenticated with it acts AS
    # that user (their current membership/role in the organization, not a
    # fixed tier frozen at creation time), the same model as a GitHub personal
    # access token. Nullable only because keys created before this column
    # existed have no recorded creator; those can no longer authenticate (cf.
    # app/core/dependencies.py's API key auth path) and must be recreated.
    user_id: Mapped[str | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
