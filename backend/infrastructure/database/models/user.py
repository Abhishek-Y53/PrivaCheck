"""User account model for authenticated PrivaCheck access.

Passwords are stored only as one-way password hashes. Hashing and password
verification belong to the authentication service, not this persistence model.
"""

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
            "length(password_hash) > 0",
            name="password_hash_nonempty",
        ),
        # Enforce case-insensitive uniqueness in PostgreSQL even if a future
        # write path accidentally bypasses application-level normalization.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
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
