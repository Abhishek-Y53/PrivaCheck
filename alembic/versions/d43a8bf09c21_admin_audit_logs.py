"""Add append-only administration audit history.

Revision ID: d43a8bf09c21
Revises: c2a7d4e91f60
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d43a8bf09c21"
down_revision: Union[str, None] = "c2a7d4e91f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(320), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])
    op.create_index("ix_admin_audit_logs_actor_created_at", "admin_audit_logs", ["actor_user_id", "created_at"])


def downgrade() -> None:
    # Downgrading destroys audit history. Never run this on live data without
    # explicit approval and an independently verified database backup.
    op.drop_index("ix_admin_audit_logs_actor_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
