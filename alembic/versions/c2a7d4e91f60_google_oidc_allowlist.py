"""Add Google identities, two roles, and platform admission rules.

Revision ID: c2a7d4e91f60
Revises: 5d8a2c1f4e90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2a7d4e91f60"
down_revision: Union[str, None] = "5d8a2c1f4e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(512), nullable=True)
    op.drop_constraint(op.f("ck_users_password_hash_nonempty"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_password_hash_nonempty"), "users", "password_hash IS NULL OR length(password_hash) > 0")
    op.add_column("users", sa.Column("google_sub", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("google_hd", sa.String(253), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(8), server_default=sa.text("'USER'"), nullable=False))
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])
    op.create_check_constraint(op.f("ck_users_google_sub_nonempty"), "users", "google_sub IS NULL OR length(google_sub) > 0")
    op.create_check_constraint(op.f("ck_users_role_allowed"), "users", "role IN ('USER', 'ADMIN')")
    op.create_check_constraint(op.f("ck_users_auth_identity_present"), "users", "password_hash IS NOT NULL OR google_sub IS NOT NULL")
    for name, selector, max_length in [
        ("platform_access_domains", "domain", 253),
        ("platform_access_emails", "email", 320),
    ]:
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(selector, sa.String(max_length), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id", name=f"pk_{name}"),
            sa.UniqueConstraint(selector, name=f"uq_{name}_{selector}"),
            sa.CheckConstraint(
                f"{selector} = lower({selector}) AND {selector} = btrim({selector})",
                name=op.f(f"ck_{name}_{selector}_canonical"),
            ),
        )
    # A fixed initial trusted Workspace domain; subsequently governed by admins.
    op.execute("INSERT INTO platform_access_domains (id, domain, is_active) VALUES (gen_random_uuid(), 'iiitg.ac.in', true)")


def downgrade() -> None:
    # Refuse to erase identity links or alter ownership when reverting the schema.
    connection = op.get_bind()
    count = connection.execute(sa.text("SELECT count(*) FROM users WHERE google_sub IS NOT NULL OR password_hash IS NULL")).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade: linked Google accounts exist. Back up/migrate users explicitly.")
    op.drop_table("platform_access_emails")
    op.drop_table("platform_access_domains")
    op.drop_constraint(op.f("ck_users_auth_identity_present"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_role_allowed"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_google_sub_nonempty"), "users", type_="check")
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    for column in ("role", "display_name", "google_hd", "google_sub"):
        op.drop_column("users", column)
    op.drop_constraint(op.f("ck_users_password_hash_nonempty"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_password_hash_nonempty"), "users", "length(password_hash) > 0")
    op.alter_column("users", "password_hash", existing_type=sa.String(512), nullable=False)
