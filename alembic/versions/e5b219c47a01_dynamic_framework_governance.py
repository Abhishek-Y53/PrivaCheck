"""Dynamic, immutable framework versions and per-framework access selectors.

Revision ID: e5b219c47a01
Revises: d43a8bf09c21
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "e5b219c47a01"
down_revision: Union[str, None] = "d43a8bf09c21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_frameworks",
        sa.Column("slug", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_compliance_frameworks_framework_status_allowed"),
    )
    op.create_table(
        "ruleset_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("framework_slug", sa.String(64), sa.ForeignKey("compliance_frameworks.slug", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("yaml_content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("rule_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("framework_slug", "version_no", name="uq_ruleset_framework_sequence"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED')", name="ck_ruleset_versions_ruleset_status_allowed"),
        sa.CheckConstraint("rule_count >= 0", name="ck_ruleset_versions_ruleset_rule_count_nonnegative"),
    )
    op.create_index("ix_ruleset_versions_framework_slug_status", "ruleset_versions", ["framework_slug", "status"])
    op.create_foreign_key("fk_frameworks_active_version", "compliance_frameworks", "ruleset_versions", ["active_version_id"], ["id"], ondelete="RESTRICT")
    op.create_table(
        "framework_access_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("framework_slug", sa.String(64), sa.ForeignKey("compliance_frameworks.slug", ondelete="RESTRICT"), nullable=False),
        sa.Column("selector_type", sa.String(12), nullable=False),
        sa.Column("selector_value", sa.String(320), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("framework_slug", "selector_type", "selector_value", name="uq_framework_access_selector"),
        sa.CheckConstraint("selector_type IN ('EVERYONE','DOMAIN','EMAIL')", name="ck_framework_access_rules_framework_selector_type_allowed"),
    )
    op.create_index("ix_framework_access_rules_slug_active", "framework_access_rules", ["framework_slug", "is_active"])
    op.add_column("scans", sa.Column("ruleset_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_scans_ruleset_version_id_ruleset_versions", "scans", "ruleset_versions", ["ruleset_version_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_scans_ruleset_version_id", "scans", ["ruleset_version_id"])

    # Seed from the project's existing, tested 42-rule GDPR YAML, not from a
    # re-authored or shortened copy. Dockerfile.backend always copies rules/.
    path = Path(__file__).resolve().parents[2] / "rules" / "gdpr" / "rules.yaml"
    content = path.read_text(encoding="utf-8")
    from backend.rule_engine.loader import RuleLoader
    rules = RuleLoader().load_text(content)
    if len(rules) != 42:
        raise RuntimeError("Expected 42 original GDPR rules; refusing unsafe bootstrap")
    version_id = uuid4()
    conn = op.get_bind()
    conn.execute(sa.text("""INSERT INTO compliance_frameworks (slug, name, description, status) VALUES ('gdpr', 'GDPR', 'Existing GDPR browser-evidence rules', 'PUBLISHED')"""))
    # Bulk insert with typed literals also produces valid offline PostgreSQL
    # migration SQL; untyped text() binds render as NULL in --sql mode.
    op.bulk_insert(sa.table("ruleset_versions",
        sa.column("id", sa.Uuid()), sa.column("framework_slug", sa.String()),
        sa.column("version_no", sa.Integer()), sa.column("status", sa.String()),
        sa.column("yaml_content", sa.Text()), sa.column("sha256", sa.String()),
        sa.column("rule_count", sa.Integer()), sa.column("published_at", sa.DateTime(timezone=True))),
        [{"id": version_id, "framework_slug": "gdpr", "version_no": 1,
          "status": "PUBLISHED", "yaml_content": content,
          "sha256": sha256(content.encode("utf-8")).hexdigest(),
          "rule_count": len(rules), "published_at": datetime.now(timezone.utc)}],
        multiinsert=False,
    )
    op.execute(f"UPDATE compliance_frameworks SET active_version_id = '{version_id}' WHERE slug = 'gdpr'")
    seed_id = uuid4()
    op.execute(f"INSERT INTO framework_access_rules (id, framework_slug, selector_type, selector_value, is_active) "
               f"VALUES ('{seed_id}', 'gdpr', 'EVERYONE', '', true)")
    # Prevent any future application code from modifying or deleting a
    # previously-published version, independently of the API layer.
    op.execute("""
        CREATE FUNCTION privacheck_protect_published_rulesets() RETURNS trigger AS $$
        BEGIN
          IF OLD.status = 'PUBLISHED' THEN
            RAISE EXCEPTION 'published ruleset versions cannot be modified or deleted';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_protect_published_rulesets
        BEFORE UPDATE OR DELETE ON ruleset_versions
        FOR EACH ROW EXECUTE FUNCTION privacheck_protect_published_rulesets()
    """)
    # Historical scans are deliberately left NULL/legacy, never falsely pinned
    # to a version they may not have used.


def downgrade() -> None:
    raise RuntimeError("Downgrading would destroy historical framework governance; restore from backup instead")
