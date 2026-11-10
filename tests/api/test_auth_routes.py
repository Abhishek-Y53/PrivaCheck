"""Offline Google authentication tests: real routes, persistence and session cookies.

Google network token exchange/signature verification is stubbed only at the
external Google boundary. Policy, state, CSRF and database sessions are real.
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes import auth as auth_routes
from backend.api.services.auth_service import hash_session_token
from backend.api.services.google_auth_service import GoogleAuthService
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models import User, UserSession, PlatformAccessDomain, PlatformAccessEmail
from backend.infrastructure.database.session import get_db
from backend.security.google_oidc import GoogleIdentity, OidcStateStore
from backend.security.passwords import hash_password
from backend.security.rate_limit import RateLimitExceeded, RateLimiterUnavailable


class FakeRedis:
    def __init__(self):
        self.items = {}

    def set(self, key, value, *, nx, ex):
        if key in self.items:
            return False
        self.items[key] = value
        return True

    def getdel(self, key):
        return self.items.pop(key, None)


class AllowAllRateLimiter:
    def enforce(self, **_kwargs):
        pass


class RejectingRateLimiter:
    def __init__(self, error):
        self.error = error

    def enforce(self, **_kwargs):
        raise self.error


@pytest.fixture()
def factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def sqlite_functions(connection, _record):
        connection.create_function("btrim", 1, lambda x: x.strip() if x else x)

    Base.metadata.create_all(engine, tables=[
        User.__table__, UserSession.__table__, PlatformAccessDomain.__table__, PlatformAccessEmail.__table__
    ])
    maker = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    yield maker
    engine.dispose()


@pytest.fixture()
def client(factory, monkeypatch) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
    )
    app.include_router(auth_routes.router)

    def override_get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(auth_routes, "auth_service", GoogleAuthService(session_factory=factory))
    monkeypatch.setattr(auth_routes, "rate_limiter", AllowAllRateLimiter())
    store = OidcStateStore()
    store._redis = FakeRedis()
    monkeypatch.setattr(auth_routes, "state_store", store)
    monkeypatch.setattr(auth_routes.settings, "GOOGLE_CLIENT_ID", "unit-test-client.apps.googleusercontent.com")
    monkeypatch.setattr(auth_routes.settings, "GOOGLE_CLIENT_SECRET", "test-only-not-real")
    monkeypatch.setattr(auth_routes, "exchange_code", lambda code, verifier: "FAKE_ID_TOKEN")
    # Identity tests override this mocked external cryptographic boundary.
    monkeypatch.setattr(auth_routes, "verify_google_identity", lambda token, nonce: GoogleIdentity(
        sub="sub-alice", email="alice@iiitg.ac.in", hd="iiitg.ac.in", name="Alice"
    ))
    with factory() as db:
        db.add(PlatformAccessDomain(domain="iiitg.ac.in"))
        db.commit()
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def google_flow(client: TestClient, *, binder: str | None = None):
    start = client.get("/auth/google/start")
    assert start.status_code == 302
    query = parse_qs(urlsplit(start.headers["location"]).query)
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["openid email profile"]
    assert "code_verifier" not in query
    state = query["state"][0]
    if binder is not None:
        client.cookies.set("privacheck_oauth", binder)
    return client.get(f"/auth/google/callback?state={state}&code=sample-code"), state


def csrf_headers(client: TestClient):
    token = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": token, "Origin": "http://localhost:5173"}


def test_google_signin_sets_revocable_httponly_session(client, factory):
    response, _ = google_flow(client)
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/"
    session_cookie = response.cookies.get("privacheck_session")
    assert session_cookie
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/auth/me").json()["role"] == "USER"
    with factory() as db:
        record = db.scalar(select(UserSession))
        user = db.scalar(select(User))
        assert record.token_hash == hash_session_token(session_cookie)
        assert user.password_hash is None
        assert user.google_sub == "sub-alice"
        assert user.email == "alice@iiitg.ac.in"
    assert client.post("/auth/register", json={}).status_code == 404
    assert client.post("/auth/login", json={}).status_code == 404


def test_state_is_one_time_and_bound_to_browser(client, factory):
    denied, state = google_flow(client, binder="wrong-browser")
    assert denied.status_code == 303
    assert "google_denied" in denied.headers["location"]
    assert client.get("/auth/me").status_code == 401
    replay = client.get(f"/auth/google/callback?state={state}&code=sample-code")
    assert "google_denied" in replay.headers["location"]
    with factory() as db:
        assert db.scalar(select(User.id)) is None


def test_domain_admission_requires_signed_hd(client, factory, monkeypatch):
    monkeypatch.setattr(auth_routes, "verify_google_identity", lambda t, n: GoogleIdentity(
        sub="not-workspace", email="someone@iiitg.ac.in", hd=None, name=None
    ))
    denied, _ = google_flow(client)
    assert "not_allowed" in denied.headers["location"]
    with factory() as db:
        assert db.scalar(select(User.id)) is None


def test_exact_external_email_admitted_and_dynamic_revocation(client, factory, monkeypatch):
    with factory() as db:
        db.add(PlatformAccessEmail(email="someone@gmail.com"))
        db.commit()
    monkeypatch.setattr(auth_routes, "verify_google_identity", lambda t, n: GoogleIdentity(
        sub="external-account", email="someone@gmail.com", hd=None, name=None
    ))
    accepted, _ = google_flow(client)
    assert accepted.headers["location"] == "http://localhost:5173/"
    assert client.get("/auth/me").status_code == 200
    with factory() as db:
        entry = db.scalar(select(PlatformAccessEmail))
        entry.is_active = False
        db.commit()
    assert client.get("/auth/me").status_code == 401
    with factory() as db:
        record = db.scalar(select(UserSession))
        assert record.revoked_at is not None


def test_admin_bypasses_allowlist_but_not_suspension(client, factory):
    google_flow(client)
    with factory() as db:
        user = db.scalar(select(User))
        user.role = "ADMIN"
        domain = db.scalar(select(PlatformAccessDomain))
        domain.is_active = False
        db.commit()
    assert client.get("/auth/me").status_code == 200
    with factory() as db:
        user = db.scalar(select(User))
        user.is_active = False
        db.commit()
    assert client.get("/auth/me").status_code == 401


def test_legacy_link_proves_password_preserves_id_and_revokes_sessions(client, factory):
    with factory() as db:
        old = User(email="alice@iiitg.ac.in", password_hash=hash_password("old secret passphrase"))
        db.add(old)
        db.commit()
        old_id = old.id
        old_session = UserSession(user_id=old.id, token_hash="a" * 64, expires_at=datetime.now(timezone.utc) + timedelta(days=1))
        db.add(old_session)
        db.commit()
    pending, _ = google_flow(client)
    assert pending.headers["location"] == "http://localhost:5173/link-account"
    assert client.get("/auth/me").status_code == 401
    token = csrf_headers(client)
    wrong = client.post("/auth/google/link", headers=token, json={"password": "incorrect"})
    assert wrong.status_code == 401
    # One-time challenge cannot be replayed after even a wrong password.
    replay = client.post("/auth/google/link", headers=token, json={"password": "old secret passphrase"})
    assert replay.status_code == 401
    pending, _ = google_flow(client)
    assert "link-account" in pending.headers["location"]
    linked = client.post("/auth/google/link", headers=csrf_headers(client), json={"password": "old secret passphrase"})
    assert linked.status_code == 200
    assert linked.json()["id"] == str(old_id)
    with factory() as db:
        user = db.get(User, old_id)
        assert user.google_sub == "sub-alice"
        assert user.password_hash is None
        sessions = list(db.scalars(select(UserSession)))
        assert len(sessions) == 1
        assert sessions[0].token_hash != "a" * 64
    assert client.get("/auth/me").status_code == 200


def test_logout_requires_csrf_and_revokes_session(client, factory):
    google_flow(client)
    assert client.post("/auth/logout").status_code == 403
    assert client.post("/auth/logout", headers=csrf_headers(client)).status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_rate_limiter_fails_closed(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "rate_limiter", RejectingRateLimiter(RateLimiterUnavailable()))
    assert client.get("/auth/google/start").status_code == 503
    monkeypatch.setattr(auth_routes, "rate_limiter", RejectingRateLimiter(RateLimitExceeded(60)))
    response = client.get("/auth/google/start")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_expired_session_rejected(client, factory):
    google_flow(client)
    with factory() as db:
        now = datetime.now(timezone.utc)
        db.execute(update(UserSession).values(created_at=now - timedelta(days=2), expires_at=now - timedelta(days=1)))
        db.commit()
    assert client.get("/auth/me").status_code == 401


def test_cors_only_allows_known_frontend(client):
    okay = client.options("/auth/google/link", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert okay.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/auth/google/link", headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"})
    assert bad.headers.get("access-control-allow-origin") is None
