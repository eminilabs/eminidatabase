from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class OAuthProviderName(str, enum.Enum):
    GOOGLE = "google"
    GITHUB = "github"


class OAuthAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links a `User` to an external identity provider account. A separate table
    rather than columns on `User` — a user can link both Google and GitHub to the
    same account (same reasoning `Payment` is its own table rather than columns
    on `Invoice`: one user, several provider links, each independently useful).

    `(provider, provider_account_id)` is the idempotency/lookup key on every
    login — the same pattern `Payment`'s `(provider, provider_payment_id)` and
    `Webhook`'s HMAC secret already establish in this codebase.
    """

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_oauth_provider_account"),
    )

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[OAuthProviderName] = mapped_column(
        Enum(OAuthProviderName, native_enum=False, length=20), nullable=False
    )
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
