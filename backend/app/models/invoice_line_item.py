from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class InvoiceLineItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("invoices.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[Numeric] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Numeric] = mapped_column(Numeric(18, 6), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
