from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class DatabaseEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "database_events"

    database_id: Mapped[str] = mapped_column(GUID(), ForeignKey("databases.id"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(GUID(), ForeignKey("jobs.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
