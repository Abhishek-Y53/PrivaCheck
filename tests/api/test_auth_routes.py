from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes import auth as auth_routes
from backend.api.services.auth_service import AuthService
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models import User, UserSession
from backend.infrastructure.database.session import get_db
from backend.security.rate_limit import RateLimitExceeded, RateLimiterUnavailable
from backend.api.services.auth_service import hash_session_token


class AllowAllRateLimiter:
    def enforce(self, **_kwargs) -> None:
        return None


class RejectingRateLimiter:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def enforce(self, **_kwargs) -> None:
        raise self.error


@pytest.fixture()
def test_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def install_btrim(dbapi_connection, _connection_record):
        dbapi_connection.create_function(
            "btrim", 1, lambda value: value.strip() if value is not None else None
        )

    Base.metadata.create_all(engine, tables=[User.__table__, UserSession.__table__])
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def client(test_session_factory, monkeypatch) -> Generator[TestClient, None, None]:
    def override_get_db():
        with test_session_factory() as db:
            yield db

    test_app = FastAPI()
    origins = [item.strip() for item in auth_routes.settings.CORS_ORIGINS.split(",")]
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
    )
    test_app.include_router(auth_routes.router)
    test_app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        auth_routes, "auth_service", AuthService(session_factory=test_session_factory)
    )
    monkeypatch.setattr(auth_routes, "rate_limiter", AllowAllRateLimiter())
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()


def get_csrf(client: TestClient) -> str:
    response = client.get("/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def csrf_headers(token: str) -> dict[str, str]:
    return {
        "X-CSRF-Token": token,
        "Origin": "http://127.0.0.1:5173",
    }


def test_registration_sets_httponly_session_and_does_not_return_secret(client, test_session_factory):
    csrf_token = get_csrf(client)
    response = client.post(
        "/auth/register",
        headers=csrf_headers(csrf_token),
        json={"email": "  Test.User@Example.com ", "password": "a secure passphrase 123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "test.user@example.com"
    assert "password_hash" not in body["user"]
    assert "session_token" not in body
    assert body["csrf_token"]

    session_cookie = response.cookies.get("privacheck_session")
    assert session_cookie
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "privacheck_session" in set_cookie

    # The persisted record contains only a digest, never the cookie secret.
    with test_session_factory() as db:
        record = db.scalar(select(UserSession))
        assert record is not None
        assert record.token_hash == hash_session_token(session_cookie)
        assert record.token_hash != session_cookie
        assert len(record.token_hash) == 64


def test_me_requires_authentication_and_returns_safe_profile(client):
    unauthenticated = client.get("/auth/me")
    assert unauthenticated.status_code == 401

    token = get_csrf(client)
    registered = client.post(
        "/auth/register",
        headers=csrf_headers(token),
        json={"email": "me@example.com", "password": "a secure passphrase 123"},
    )
    assert registered.status_code == 201

    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"
    assert "password_hash" not in response.json()


def test_logout_revokes_session_and_clears_cookies(client):
    token = get_csrf(client)
    registered = client.post(
        "/auth/register",
        headers=csrf_headers(token),
        json={"email": "logout@example.com", "password": "a secure passphrase 123"},
    )
    assert registered.status_code == 201

    logout_csrf = registered.json()["csrf_token"]
    response = client.post("/auth/logout", headers=csrf_headers(logout_csrf))
    assert response.status_code == 204

    me = client.get("/auth/me")
    assert me.status_code == 401


def test_login_works_and_wrong_password_is_generic(client):
    csrf_token = get_csrf(client)
    registered = client.post(
        "/auth/register",
        headers=csrf_headers(csrf_token),
        json={"email": "login@example.com", "password": "a secure passphrase 123"},
    )
    assert registered.status_code == 201
    client.post("/auth/logout", headers=csrf_headers(registered.json()["csrf_token"]))

    login_csrf = get_csrf(client)
    logged_in = client.post(
        "/auth/login",
        headers=csrf_headers(login_csrf),
        json={"email": "LOGIN@example.com", "password": "a secure passphrase 123"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["email"] == "login@example.com"

    wrong_csrf = logged_in.json()["csrf_token"]
    client.post("/auth/logout", headers=csrf_headers(wrong_csrf))
    login_csrf = get_csrf(client)
    bad_login = client.post(
        "/auth/login",
        headers=csrf_headers(login_csrf),
        json={"email": "login@example.com", "password": "incorrect password"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["detail"] == "Email or password is incorrect."


def test_mutating_auth_endpoint_rejects_missing_csrf_and_untrusted_origin(client):
    missing_csrf = client.post(
        "/auth/register",
        json={"email": "csrf@example.com", "password": "a secure passphrase 123"},
    )
    assert missing_csrf.status_code == 403

    token = get_csrf(client)
    untrusted = client.post(
        "/auth/register",
        headers={"X-CSRF-Token": token, "Origin": "https://attacker.example"},
        json={"email": "csrf@example.com", "password": "a secure passphrase 123"},
    )
    assert untrusted.status_code == 403


def test_registration_duplicate_email_returns_conflict(client):
    csrf_token = get_csrf(client)
    payload = {"email": "duplicate@example.com", "password": "a secure passphrase 123"}
    first = client.post("/auth/register", headers=csrf_headers(csrf_token), json=payload)
    assert first.status_code == 201

    next_csrf = first.json()["csrf_token"]
    second = client.post("/auth/register", headers=csrf_headers(next_csrf), json=payload)
    assert second.status_code == 409


def test_auth_rate_limit_fails_closed_when_valkey_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        auth_routes,
        "rate_limiter",
        RejectingRateLimiter(RateLimiterUnavailable()),
    )
    token = get_csrf(client)
    response = client.post(
        "/auth/login",
        headers=csrf_headers(token),
        json={"email": "nobody@example.com", "password": "a secure passphrase 123"},
    )
    assert response.status_code == 503


def test_auth_rate_limit_returns_retry_after(client, monkeypatch):
    monkeypatch.setattr(
        auth_routes,
        "rate_limiter",
        RejectingRateLimiter(RateLimitExceeded(60)),
    )
    token = get_csrf(client)
    response = client.post(
        "/auth/login",
        headers=csrf_headers(token),
        json={"email": "nobody@example.com", "password": "a secure passphrase 123"},
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_credentialed_cors_allows_only_configured_frontend_origins(client):
    allowed = client.options(
        "/auth/login",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"

    denied = client.options(
        "/auth/login",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_logout_is_idempotent_for_an_expired_or_missing_session(client):
    token = get_csrf(client)
    response = client.post("/auth/logout", headers=csrf_headers(token))
    assert response.status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_expired_session_is_rejected(client, test_session_factory):
    csrf_token = get_csrf(client)
    registered = client.post(
        "/auth/register",
        headers=csrf_headers(csrf_token),
        json={"email": "expired@example.com", "password": "a secure passphrase 123"},
    )
    assert registered.status_code == 201

    with test_session_factory() as db:
        now = datetime.now(timezone.utc)
        db.execute(
            update(UserSession).values(
                created_at=now - timedelta(days=2),
                expires_at=now - timedelta(days=1),
            )
        )
        db.commit()

    assert client.get("/auth/me").status_code == 401


def test_inactive_account_cannot_use_existing_session(client, test_session_factory):
    csrf_token = get_csrf(client)
    registered = client.post(
        "/auth/register",
        headers=csrf_headers(csrf_token),
        json={"email": "inactive@example.com", "password": "a secure passphrase 123"},
    )
    assert registered.status_code == 201

    with test_session_factory() as db:
        user = db.scalar(select(User).where(User.email == "inactive@example.com"))
        assert user is not None
        user.is_active = False
        db.commit()

    assert client.get("/auth/me").status_code == 401
