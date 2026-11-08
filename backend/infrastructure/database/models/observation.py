"""Short-lived crawler observations used by the compliance evaluator."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infrastructure.database.base import Base


class ScanObservation(Base):
    """One crawler observation associated with a scan.

    Observation payloads can contain sensitive browser-derived values. These
    rows are staging data, not permanent report evidence. The worker must
    delete them after evaluation, with ``expires_at`` as a cleanup backstop.
    Access should be restricted to the crawler/compliance execution path.
    """

    __tablename__ = "scan_observations"
    __table_args__ = (
        Index("ix_scan_observations_scan_id", "scan_id"),
        Index("ix_scan_observations_expires_at", "expires_at"),
        Index("ix_scan_observations_scan_category", "scan_id", "category"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    scan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("(CURRENT_TIMESTAMP + INTERVAL '24 hours')"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scan: Mapped["Scan"] = relationship(back_populates="observations")
