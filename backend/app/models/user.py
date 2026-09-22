from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import Membership


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    # Null for an account created via OAuth only (Google/GitHub) that never set a
    # password — cf. app/services/oauth_service.py.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Platform-level administration (nodes, regions) is a distinct concern from
    # organization RBAC — an org owner has no inherent right to manage infrastructure.
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # Bumped by /auth/sessions/revoke-all to invalidate every previously
    # issued JWT at once (they carry the version at issuance time in their
    # `ver` claim, cf. app/core/security.py) — no per-token session table to
    # maintain, "sign out everywhere" is just incrementing one integer.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
