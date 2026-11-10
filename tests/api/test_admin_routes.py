"""Route-level admin permission, CSRF, reauthentication and scan audit tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text, DefaultClause
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.dependencies.auth import get_current_user
from backend.api.routes.admin import router as admin_router
from backend.api.services.auth_service import hash_session_token
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.admin_audit_log import AdminAuditLog
from backend.infrastructure.database.models.check_result import CheckResultRecord
from backend.infrastructure.database.models.platform_access import PlatformAccessDomain, PlatformAccessEmail
from backend.infrastructure.database.models.scan import Scan
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.session import get_db


@compiles(JSONB, "sqlite")
def jsonb_as_json(_type, _compiler, **_kw):
    return "JSON"


@pytest.fixture()
def setup():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def sqlite_helpers(conn, _rec):
        conn.create_function("btrim", 1, lambda value: value.strip() if value else value)
    # This production column has a PostgreSQL-specific ::jsonb server default.
    # Temporarily use an equivalent SQLite default only for this test schema.
    json_default = Scan.__table__.c["metadata"].server_default
    Scan.__table__.c["metadata"].server_default = DefaultClause(text("'{}'"))
    try:
        Base.metadata.create_all(engine, tables=[
        User.__table__, UserSession.__table__, PlatformAccessDomain.__table__,
        PlatformAccessEmail.__table__, AdminAuditLog.__table__, Scan.__table__,
        CheckResultRecord.__table__,
        ])
    finally:
        Scan.__table__.c["metadata"].server_default = json_default
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    token = "a-revocable-admin-session-token"
    with factory() as db:
        admin = User(email="admin@gmail.com", google_sub="admin-google", is_active=True, role="ADMIN")
        regular = User(email="student@iiitg.ac.in", google_sub="student-google", google_hd="iiitg.ac.in", role="USER")
        db.add_all([admin, regular])
        db.flush()
        db.add(UserSession(user_id=admin.id, token_hash=hash_session_token(token),
                           expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        db.add(Scan(user_id=regular.id, website="https://example.com/?secret=do-not-expose", framework="gdpr",
                    lifecycle_status="COMPLETED", compliance_status="PASS", risk_score=0.0,
                    total_checks=0, passed_checks=0, failed_checks=0, observation_count=0))
        db.commit()
        ids = (admin.id, regular.id)

    app = FastAPI()
    app.include_router(admin_router)
    actor = [ids[0]]

    def override_db():
        with factory() as db:
            yield db

    def override_user():
        with factory() as db:
            return db.get(User, actor[0])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        client.cookies.set("privacheck_session", token)
        client.cookies.set("privacheck_csrf", "test-double-submit-token")
        yield client, factory, ids, actor
    app.dependency_overrides.clear()
    engine.dispose()


def csrf():
    return {"X-CSRF-Token": "test-double-submit-token", "Origin": "http://localhost:5173"}


def test_non_admin_cannot_list_or_modify_users(setup):
    client, factory, (admin_id, user_id), actor = setup
    actor[0] = user_id
    assert client.get('/admin/users').status_code == 403
    assert client.get('/admin/scans').status_code == 403
    assert client.get('/admin/audit').status_code == 403
    assert client.post(f'/admin/users/{admin_id}/role', json={"role":"USER"}, headers=csrf()).status_code == 403


def test_mutating_routes_require_csrf(setup):
    client, _, (_, user_id), _ = setup
    assert client.post(f'/admin/users/{user_id}/role', json={"role":"ADMIN"}).status_code == 403
    assert client.post('/admin/allowlist/emails', json={"value": "other@gmail.com", "is_active":True}).status_code == 403


def test_admin_can_promote_and_audit_and_prevent_self_change(setup):
    client, factory, (admin_id, user_id), _ = setup
    forbidden = client.post(f'/admin/users/{admin_id}/status', json={"is_active":False}, headers=csrf())
    assert forbidden.status_code == 409
    success = client.post(f'/admin/users/{user_id}/role', json={"role":"ADMIN"}, headers=csrf())
    assert success.status_code == 200, success.text
    assert success.json()['role'] == 'ADMIN'
    audit = client.get('/admin/audit')
    assert audit.status_code == 200
    assert audit.json()['items'][0]['action'] == 'user.role.changed'
    with factory() as db:
        assert db.get(User, user_id).role == 'ADMIN'


def test_recent_google_session_required_for_sensitive_updates(setup):
    client, factory, (admin_id, user_id), _ = setup
    with factory() as db:
        session = db.scalar(select(UserSession).where(UserSession.user_id == admin_id))
        session.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    old_session = client.post(f'/admin/users/{user_id}/status', json={"is_active":False}, headers=csrf())
    assert old_session.status_code == 403
    assert 'Recent Google sign-in' in old_session.json()['detail']


def test_allowlist_checks_exact_email_and_audits_mutation(setup):
    client, _, _, _ = setup
    response = client.post('/admin/allowlist/domains', json={"value":"*.iiitg.ac.in", "is_active":True}, headers=csrf())
    assert response.status_code == 422
    response = client.post('/admin/allowlist/emails', json={"value":"GUEST@GMAIL.COM", "is_active":True}, headers=csrf())
    assert response.status_code == 200, response.text
    assert response.json()['value'] == 'guest@gmail.com'
    assert len(client.get('/admin/allowlist').json()['emails']) == 1
    response = client.post('/admin/allowlist/emails', json={"value":"guest@gmail.com", "is_active":False}, headers=csrf())
    assert response.status_code == 200
    assert response.json()['is_active'] is False


def test_admin_other_users_report_access_is_audited_and_redacted(setup):
    client, factory, (_, user_id), _ = setup
    history = client.get('/admin/scans')
    assert history.status_code == 200, history.text
    assert history.json()['total'] == 1
    scan_id = history.json()['items'][0]['scan']['scan_id']
    status_result = client.get(f'/admin/scans/{scan_id}')
    assert status_result.status_code == 200, status_result.text
    assert 'secret' not in status_result.text
    report = client.get(f'/admin/scans/{scan_id}/report')
    assert report.status_code == 200, report.text
    assert report.json()['risk_score'] == 0.0
    with factory() as db:
        assert db.scalar(select(AdminAuditLog).where(AdminAuditLog.action == 'report.viewed')) is not None
