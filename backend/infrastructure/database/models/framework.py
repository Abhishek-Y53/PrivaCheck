"""Versioned compliance frameworks and exact-selector access policies."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infrastructure.database.base import Base


class ComplianceFramework(Base):
    __tablename__ = "compliance_frameworks"
    __table_args__ = (CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="framework_status_allowed"),)

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'DRAFT'"))
    active_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ruleset_versions.id", name="fk_frameworks_active_version", ondelete="RESTRICT"), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    versions: Mapped[list["RulesetVersion"]] = relationship("RulesetVersion", back_populates="framework", foreign_keys="RulesetVersion.framework_slug", order_by="RulesetVersion.version_no")
    selectors: Mapped[list["FrameworkAccessRule"]] = relationship("FrameworkAccessRule", back_populates="framework")


class RulesetVersion(Base):
    __tablename__ = "ruleset_versions"
    __table_args__ = (
        UniqueConstraint("framework_slug", "version_no", name="uq_ruleset_framework_sequence"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED')", name="ruleset_status_allowed"),
        CheckConstraint("rule_count >= 0", name="ruleset_rule_count_nonnegative"),
        Index("ix_ruleset_versions_framework_slug_status", "framework_slug", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    framework_slug: Mapped[str] = mapped_column(String(64), ForeignKey("compliance_frameworks.slug", ondelete="RESTRICT"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'DRAFT'"))
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    published_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    framework: Mapped[ComplianceFramework] = relationship("ComplianceFramework", back_populates="versions", foreign_keys=[framework_slug])


class FrameworkAccessRule(Base):
    __tablename__ = "framework_access_rules"
    __table_args__ = (
        UniqueConstraint("framework_slug", "selector_type", "selector_value", name="uq_framework_access_selector"),
        CheckConstraint("selector_type IN ('EVERYONE','DOMAIN','EMAIL')", name="framework_selector_type_allowed"),
        Index("ix_framework_access_rules_slug_active", "framework_slug", "is_active"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    framework_slug: Mapped[str] = mapped_column(String(64), ForeignKey("compliance_frameworks.slug", ondelete="RESTRICT"), nullable=False)
    selector_type: Mapped[str] = mapped_column(String(12), nullable=False)
    selector_value: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    framework: Mapped[ComplianceFramework] = relationship("ComplianceFramework", back_populates="selectors")
