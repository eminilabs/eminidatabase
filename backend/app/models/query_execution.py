from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class QueryExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """SQL Editor history (cahier des charges §35 — 'historique', 'temps
    d'exécution', 'erreurs'). One row per execution, successful or not."""

    __tablename__ = "query_executions"

    database_id: Mapped[str] = mapped_column(GUID(), ForeignKey("databases.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    query_text: Mapped[str] = mapped_column(String(10000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # succeeded|failed
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
