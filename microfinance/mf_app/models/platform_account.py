"""The microfinance service's own, single Control Plane identity.

One record, created once by scripts/bootstrap_platform_account.py (cf.
docs/architecture/08 §8.4) — the service authenticates to the platform as this
one CP user/organization for every institution it onboards, exactly like any
third-party developer using the SDK would.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.control_base import ControlBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class MFPlatformAccount(UUIDPrimaryKeyMixin, TimestampMixin, ControlBase):
    __tablename__ = "mf_platform_accounts"

    cp_organization_id: Mapped[str] = mapped_column(GUID(), nullable=False)
    cp_email: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_cp_password: Mapped[str] = mapped_column(String(500), nullable=False)

    # Cached JWT so every request doesn't need to re-login; refreshed lazily by
    # app/services/platform_client.py once it's within a minute of expiring.
    cached_access_token: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    token_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
