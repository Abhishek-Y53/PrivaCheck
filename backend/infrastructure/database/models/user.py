"""PrivaCheck user accounts keyed by UUID and Google OIDC subject."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infrastructure.database.base import Base


class User(Base):
    """An application account that may own website scans."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email = lower(email) AND email = btrim(email) "
            "AND length(email) BETWEEN 3 AND 320",
            name="email_canonical",
        ),
        CheckConstraint(
            "password_hash IS NULL OR length(password_hash) > 0",
            name="password_hash_nonempty",
        ),
        CheckConstraint("role IN ('USER', 'ADMIN')", name="role_allowed"),
        CheckConstraint("password_hash IS NOT NULL OR google_sub IS NOT NULL", name="auth_identity_present"),
        CheckConstraint("google_sub IS NULL OR length(google_sub) > 0", name="google_sub_nonempty"),
        # Enforce case-insensitive uniqueness in PostgreSQL even if a future
        # write path accidentally bypasses application-level normalization.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Non-null only until a legacy password account is explicitly linked.
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    google_hd: Mapped[str | None] = mapped_column(String(253), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(8), nullable=False, default="USER", server_default=text("'USER'"))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    scans: Mapped[list["Scan"]] = relationship(
        "Scan",
        back_populates="user",
        # Let PostgreSQL enforce ON DELETE RESTRICT. Without "all", the ORM
        # may NULL child user_id values when a loaded user is deleted.
        passive_deletes="all",
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
