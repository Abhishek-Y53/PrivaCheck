"""Admin-managed, exact-match admission allowlists (no wildcard domains)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class PlatformAccessDomain(Base):
    __tablename__ = "platform_access_domains"
    __table_args__ = (
        CheckConstraint("domain = lower(domain) AND domain = btrim(domain)", name="domain_canonical"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    domain: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PlatformAccessEmail(Base):
    __tablename__ = "platform_access_emails"
    __table_args__ = (
        CheckConstraint("email = lower(email) AND email = btrim(email)", name="email_canonical"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
