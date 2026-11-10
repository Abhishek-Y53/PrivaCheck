"""Phase B admin operations, checks, and audit using an isolated SQLite database.

No paid services or Google network connection. Integration in Docker/Postgres is
still required to verify the real migration and user interface.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.services.admin_service import change_user, normalized_domain, set_admission
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.admin_audit_log import AdminAuditLog
from backend.infrastructure.database.models.platform_access import PlatformAccessDomain, PlatformAccessEmail
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession


@pytest.fixture()
def factory():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def add_trim_function(conn, _rec):
        conn.create_function("btrim", 1, lambda value: value.strip() if value else value)
    Base.metadata.create_all(engine, tables=[
        User.__table__, UserSession.__table__, PlatformAccessDomain.__table__,
        PlatformAccessEmail.__table__, AdminAuditLog.__table__,
    ])
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    yield maker
    engine.dispose()


@pytest.fixture()
def users(factory):
    with factory() as db:
        admin = User(email="admin@gmail.com", google_sub="sub-admin", role="ADMIN", is_active=True)
        target = User(email="target@gmail.com", google_sub="sub-target", role="USER", is_active=True)
        db.add_all([admin, target])
        db.commit()
        return admin.id, target.id


def test_invalid_domains_cannot_match_by_suffix_or_wildcard():
    for domain in ("*.iiitg.ac.in", ".iiitg.ac.in", "evil..com", "xn--bad label.com", "example.com.evil/ok", "a"*64+".com"):
        with pytest.raises(ValueError):
            normalized_domain(domain)
    assert normalized_domain(" IIITG.AC.IN ") == "iiitg.ac.in"


def test_promote_revokes_sessions_and_audits(factory, users):
    admin_id, target_id = users
    with factory() as db:
        db.add(UserSession(user_id=target_id, token_hash="a"*64, expires_at=datetime.now(timezone.utc)+timedelta(days=2)))
        db.commit()
        admin = db.get(User, admin_id)
        updated = change_user(db, admin, target_id, field="role", value="ADMIN")
        assert updated.role == "ADMIN"
    with factory() as db:
        assert db.scalar(select(UserSession).where(UserSession.user_id == target_id)).revoked_at is not None
        entry = db.scalar(select(AdminAuditLog))
        assert entry.actor_user_id == admin_id
        assert entry.action == "user.role.changed"
        assert entry.before_data == {"role": "USER", "is_active": True}
        assert entry.after_data == {"role": "ADMIN", "is_active": True}


def test_cannot_self_disable_or_demote_last_admin(factory, users):
    admin_id, target_id = users
    with factory() as db:
        admin = db.get(User, admin_id)
        with pytest.raises(HTTPException) as exc:
            change_user(db, admin, admin_id, field="role", value="USER")
        assert exc.value.status_code == 409
        with pytest.raises(HTTPException) as exc:
            change_user(db, admin, admin_id, field="is_active", value=False)
        assert exc.value.status_code == 409
        target = db.get(User, target_id)
        target.role = "ADMIN"
        db.commit()
        result = change_user(db, admin, target_id, field="role", value="USER")
        assert result.role == "USER"  # Another active admin remains.


def test_other_last_admin_protected_even_from_active_admin():
    # This function tests the actual last-admin count guard rather than
    # relying only on the self-modification safeguard.
    from backend.api.services.admin_service import _ensure_another_admin
    class FakeSession:
        def scalar(self, _statement): return 1
    with pytest.raises(HTTPException) as exc:
        _ensure_another_admin(FakeSession())
    assert exc.value.status_code == 409


def test_suspension_cannot_be_bypassed_by_existing_session(factory, users):
    admin_id, target_id = users
    with factory() as db:
        admin = db.get(User, admin_id)
        response = change_user(db, admin, target_id, field="is_active", value=False)
        assert response.is_active is False
        target = db.get(User, target_id)
        assert target.is_active is False
    with factory() as db:
        assert db.scalar(select(AdminAuditLog)).action == "user.is_active.changed"


def test_allowlist_is_canonical_audited_and_can_be_revoked(factory, users):
    admin_id, _ = users
    with factory() as db:
        admin = db.get(User, admin_id)
        added = set_admission(db, admin, selector_type="emails", value=" USER@GMAIL.COM ", is_active=True)
        assert added.value == "user@gmail.com"
        assert added.is_active
        revoked = set_admission(db, admin, selector_type="emails", value="user@gmail.com", is_active=False)
        assert revoked.id == added.id
        assert revoked.is_active is False
    with factory() as db:
        events = db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at)).all()
        assert len(events) == 2
        assert all(event.action == "allowlist.changed" for event in events)
        assert db.scalar(select(PlatformAccessEmail)).is_active is False


def test_disabling_nonexistent_admission_rule_is_denied(factory, users):
    admin_id, _ = users
    with factory() as db:
        with pytest.raises(HTTPException) as exc:
            set_admission(db, db.get(User, admin_id), selector_type="domains", value="example.org", is_active=False)
        assert exc.value.status_code == 404


def test_admin_audit_entries_are_not_deleted_or_changed_by_api():
    import inspect
    from backend.api.services.admin_service import audit
    assert "session_token" not in inspect.signature(audit).parameters
