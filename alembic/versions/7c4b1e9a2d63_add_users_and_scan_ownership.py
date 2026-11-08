"""add users and nullable scan ownership

Revision ID: 7c4b1e9a2d63
Revises: 609e57c75bf0
Create Date: 2026-11-06

Existing scans intentionally remain ownerless (user_id NULL). They are not
silently assigned to the first account that registers. A later controlled
administrative adoption flow can assign them to an authorized account.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c4b1e9a2d63"
down_revision: Union[str, None] = "609e57c75bf0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email = lower(email) AND email = btrim(email) "
            "AND length(email) BETWEEN 3 AND 320",
            name="email_canonical",
        ),
        sa.CheckConstraint(
            "length(password_hash) > 0",
            name="password_hash_nonempty",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )

    # Keep nullable while accounts are introduced. Historical scans must not
    # be deleted or assigned to an arbitrary user during this migration.
    op.add_column("scans", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_scans_user_id_users",
        "scans",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_scans_user_id_created_at",
        "scans",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Downgrade removes ownership metadata but leaves scan rows intact.
    op.drop_index("ix_scans_user_id_created_at", table_name="scans")
    op.drop_constraint("fk_scans_user_id_users", "scans", type_="foreignkey")
    op.drop_column("scans", "user_id")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
