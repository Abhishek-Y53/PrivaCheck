"""Persisted, sanitized compliance finding for one scan and one rule."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infrastructure.database.base import Base


class CheckResultRecord(Base):
    """Sanitized result of evaluating one configured compliance rule."""

    __tablename__ = "check_results"
    __table_args__ = (
        UniqueConstraint("scan_id", "check_id", name="uq_check_result_per_scan"),
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'WARNING', 'MANUAL_REVIEW', 'NOT_APPLICABLE')",
            name="status_valid",
        ),
        CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')",
            name="severity_valid",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="confidence_range"
        ),
        Index("ix_check_results_scan_id", "scan_id"),
        Index("ix_check_results_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    scan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Evidence here must come from the sanitized CheckResult produced by
    # report_builder.sanitize_check_result, never the raw evaluator object.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scan: Mapped["Scan"] = relationship(back_populates="check_results")
