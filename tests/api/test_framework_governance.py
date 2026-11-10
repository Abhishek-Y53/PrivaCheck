"""Isolated SQLite governance tests; PostgreSQL migration has separate checks."""
from __future__ import annotations

from uuid import uuid4, UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.infrastructure.database import models  # noqa: F401 - load ORM class registry
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.admin_audit_log import AdminAuditLog
from backend.infrastructure.database.models.framework import ComplianceFramework, FrameworkAccessRule, RulesetVersion
from backend.api.services.framework_service import (
    is_allowed, save_draft, publish, replace_access, validate_rules, set_archived, current_version,
)
from backend.rule_engine.loader import RuleLoader

YAML = '''rules:
  - id: CUSTOM-001
    name: Example consent check
    description: test
    category: PRIVACY
    source: {observation: dom_button, match: any}
    evaluator: declarative
    conditions:
      any:
        - {field: text, operator: contains, value: privacy}
    result: {pass: PASS, fail: FAIL}
    severity: MEDIUM
'''


@pytest.fixture
def storage():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def register_sqlite_helpers(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip() if value else value)
    Base.metadata.create_all(engine, tables=[User.__table__, ComplianceFramework.__table__, RulesetVersion.__table__,
                                            FrameworkAccessRule.__table__, AdminAuditLog.__table__])
    with Session(engine, expire_on_commit=False) as db:
        admin = User(id=uuid4(), email="admin@gmail.com", google_sub="admin-sub", role="ADMIN", is_active=True)
        college = User(id=uuid4(), email="student@iiitg.ac.in", google_sub="stu-sub", google_hd="iiitg.ac.in", role="USER", is_active=True)
        imposter = User(id=uuid4(), email="other@iiitg.ac.in", google_sub="other-sub", google_hd=None, role="USER", is_active=True)
        gmail = User(id=uuid4(), email="approved@gmail.com", google_sub="email-sub", role="USER", is_active=True)
        db.add_all([admin, college, imposter, gmail]); db.commit()
        fw = ComplianceFramework(slug="custom", name="Custom Privacy", description="Test rules", status="DRAFT", created_by=admin.id)
        db.add(fw); db.commit()
        yield db, admin, college, imposter, gmail, fw
    engine.dispose()


def test_gdpr_original_rule_set_is_compatible():
    assert len(RuleLoader().load('rules/gdpr/rules.yaml')) == 42


def test_validation_rejects_unsafe_and_unsupported_rules():
    assert validate_rules(YAML) == 1
    with pytest.raises(Exception):
        RuleLoader().load_text("!!python/object/apply:os.system ['whoami']")
    with pytest.raises((ValueError, HTTPException)):
        RuleLoader().load_text(YAML.replace('contains', 'unsafe_python'))
    with pytest.raises(HTTPException):
        validate_rules(YAML.replace('declarative', 'state_diff'))


def test_exact_domain_requires_signed_workspace_claim(storage):
    db, admin, college, imposter, gmail, fw = storage
    saved = save_draft(db, admin, fw.slug, YAML)
    publish(db, admin, fw.slug, UUID(saved['id']))
    replace_access(db, admin, fw.slug, everyone=False, domains=['iiitg.ac.in'], emails=[])
    assert is_allowed(db, admin, fw.slug)
    assert is_allowed(db, college, fw.slug)
    assert not is_allowed(db, imposter, fw.slug)
    assert not is_allowed(db, gmail, fw.slug)
    replace_access(db, admin, fw.slug, everyone=False, domains=[], emails=['approved@gmail.com'])
    assert not is_allowed(db, college, fw.slug)
    assert is_allowed(db, gmail, fw.slug)
    assert not is_allowed(db, imposter, fw.slug)


def test_revocation_immediately_prevents_access_to_existing_framework(storage):
    db, admin, college, imposter, gmail, fw = storage
    saved = save_draft(db, admin, fw.slug, YAML)
    publish(db, admin, fw.slug, UUID(saved['id']))
    replace_access(db, admin, fw.slug, everyone=True, domains=[], emails=[])
    assert is_allowed(db, gmail, fw.slug)
    replace_access(db, admin, fw.slug, everyone=False, domains=[], emails=[])
    assert not is_allowed(db, gmail, fw.slug)
    assert is_allowed(db, admin, fw.slug)
    assert db.get(RulesetVersion, UUID(saved['id'])) is not None
    assert len(db.scalars(select(AdminAuditLog).where(AdminAuditLog.action=='framework.access.changed')).all()) == 2


def test_published_version_immutable_and_new_version_does_not_rewrite_first(storage):
    db, admin, college, imposter, gmail, fw = storage
    v1 = save_draft(db, admin, fw.slug, YAML)
    publish(db, admin, fw.slug, UUID(v1['id']))
    version_one = db.get(RulesetVersion, UUID(v1['id']))
    checksum = version_one.sha256
    with pytest.raises(HTTPException) as error:
        save_draft(db, admin, fw.slug, YAML + '\n', version_one.id)
    assert error.value.status_code == 409
    v2 = save_draft(db, admin, fw.slug, YAML.replace('Example consent check', 'Updated privacy check'))
    publish(db, admin, fw.slug, UUID(v2['id']))
    assert db.get(RulesetVersion, UUID(v1['id'])).sha256 == checksum
    assert db.get(RulesetVersion, UUID(v2['id'])).sha256 != checksum
    assert current_version(db, fw).id == UUID(v2['id'])
    assert db.get(RulesetVersion, UUID(v1['id'])).status == 'PUBLISHED'


def test_archive_blocks_new_uses_and_preserves_versions(storage):
    db, admin, college, imposter, gmail, fw = storage
    draft = save_draft(db, admin, fw.slug, YAML)
    publish(db, admin, fw.slug, UUID(draft['id']))
    replace_access(db, admin, fw.slug, everyone=True, domains=[], emails=[])
    set_archived(db, admin, fw.slug, True)
    assert not is_allowed(db, gmail, fw.slug)
    assert not is_allowed(db, admin, fw.slug)
    assert db.get(RulesetVersion, UUID(draft['id'])).status == 'PUBLISHED'
    set_archived(db, admin, fw.slug, False)
    assert is_allowed(db, gmail, fw.slug)
