"""DB-backed job queue for this service — same pattern as backend/app/services/
jobs.py (cf. §8.5): the table itself is the queue, no separate broker, because a
single worker is enough at this stage and it keeps the deployable to one moving
part. Currently used for onboard_institution (SDK calls + tenant migrations can
be slow, must be retryable, never inline in the onboarding HTTP request)."""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mf_app.db.control_base import ControlBase, TimestampMixin, UUIDPrimaryKeyMixin
from mf_app.db.types import GUID


class MFJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"


class MFJob(UUIDPrimaryKeyMixin, TimestampMixin, ControlBase):
    __tablename__ = "mf_jobs"

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[MFJobStatus] = mapped_column(
        Enum(MFJobStatus, native_enum=False, length=20),
        default=MFJobStatus.QUEUED,
        nullable=False,
    )

    institution_id: Mapped[str | None] = mapped_column(GUID(), nullable=True)

    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_run_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
