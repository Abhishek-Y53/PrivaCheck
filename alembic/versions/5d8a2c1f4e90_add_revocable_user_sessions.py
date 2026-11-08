"""add revocable database-backed user sessions

Revision ID: 5d8a2c1f4e90
Revises: 7c4b1e9a2d63
Create Date: 2026-11-06

Only SHA-256 hashes of random session secrets are stored. The plaintext secret
is returned once as an HttpOnly cookie and cannot be recovered from the DB.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5d8a2c1f4e90"
down_revision: Union[str, None] = "7c4b1e9a2d63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(token_hash) = 64", name="token_hash_sha256"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="expires_after_created"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_user_sessions_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index(
        "ix_user_sessions_user_id_expires_at",
        "user_sessions",
        ["user_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_sessions_user_id_expires_at", table_name="user_sessions"
    )
    op.drop_table("user_sessions")
