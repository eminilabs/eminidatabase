from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class SavedQuery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Named, reusable queries (cahier des charges §35 — 'sauvegarde de requêtes')."""

    __tablename__ = "saved_queries"

    database_id: Mapped[str] = mapped_column(GUID(), ForeignKey("databases.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    query_text: Mapped[str] = mapped_column(String(10000), nullable=False)
