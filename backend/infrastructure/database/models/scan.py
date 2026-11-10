"""API-owned scan lifecycle and report-summary record."""

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
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infrastructure.database.base import Base


class Scan(Base):
    """One requested website assessment.

    ``lifecycle_status`` describes execution progress. ``compliance_status``
    describes the assessment outcome; they are intentionally separate.
    """

    __tablename__ = "scans"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="lifecycle_status_valid",
        ),
        CheckConstraint(
            "compliance_status IS NULL OR compliance_status IN "
            "('PASS', 'FAIL', 'WARNING', 'MANUAL_REVIEW', 'NOT_APPLICABLE')",
            name="compliance_status_valid",
        ),
        CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name="risk_score_range",
        ),
        CheckConstraint("total_checks >= 0", name="total_checks_nonnegative"),
        CheckConstraint("passed_checks >= 0", name="passed_checks_nonnegative"),
        CheckConstraint("failed_checks >= 0", name="failed_checks_nonnegative"),
        CheckConstraint(
            "observation_count >= 0", name="observation_count_nonnegative"
        ),
        Index("ix_scans_created_at", "created_at"),
        Index("ix_scans_lifecycle_status", "lifecycle_status"),
        Index("ix_scans_user_id_created_at", "user_id", "created_at"),
        Index("ix_scans_ruleset_version_id", "ruleset_version_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    website: Mapped[str] = mapped_column(String(2048), nullable=False)
    framework: Mapped[str] = mapped_column(String(64), nullable=False, default="gdpr")

    # Nullable during the ownership rollout so pre-authentication scans remain
    # intact. New API-created scans will require an authenticated owner in M8.1.3.
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # NULL identifies historical/unversioned scans created before governance.
    ruleset_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ruleset_versions.id", ondelete="RESTRICT"), nullable=True
    )

    lifecycle_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUEUED", server_default=text("'QUEUED'")
    )
    compliance_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    total_checks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    passed_checks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failed_checks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    observation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # The Python attribute is report_metadata because DeclarativeBase reserves
    # the attribute name ``metadata``. The SQL column remains named metadata.
    report_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    observations: Mapped[list["ScanObservation"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    check_results: Mapped[list["CheckResultRecord"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CheckResultRecord.check_id",
    )
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="scans",
    )

