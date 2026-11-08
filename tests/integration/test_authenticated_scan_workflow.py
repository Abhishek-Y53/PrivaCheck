"""Integration coverage for authentication, scan ownership, persistence and reports.

The test uses an isolated in-memory SQLite database and a fake Celery producer.
It exercises the real FastAPI routes, authentication service, session lookup,
SQLAlchemy repositories and asynchronous scan service. The actual crawler and
compliance worker processes are covered by the live smoke-test runbook.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.main import app
from backend.api.routes import auth as auth_routes
from backend.api.routes import scans as scan_routes
from backend.api.services.auth_service import AuthService
from backend.api.services.async_scan_service import AsyncScanService
from backend.infrastructure.database.models import User, UserSession
from backend.infrastructure.database.session import get_db
from backend.infrastructure.database.repositories.scan_repository import ScanRepository
from backend.rule_engine.framework_registry import FrameworkRegistry


FRONTEND_ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "A strong test passphrase 2026"


class AllowAllRateLimiter:
    """Remove Valkey from this isolated API integration test."""

    def enforce(self, **_kwargs: Any) -> None:
        return None


class RecordingTaskProducer:
    """Record the small task envelope without starting an external worker."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def send_task(self, task_name: str, **kwargs: Any) -> SimpleNamespace:
        self.messages.append((task_name, kwargs))
        return SimpleNamespace(id=kwargs.get("task_id", "integration-task"))


@pytest.fixture()
def database_factory() -> Generator[sessionmaker[Session], None, None]:
    """Create a dedicated in-memory database with only the tables this test uses.

    PostgreSQL JSONB columns are represented as SQLite JSON in this test-only
    schema. No production model or migration is altered to support SQLite.
    """
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function(
            "btrim", 1, lambda value: value.strip() if value is not None else None
        )
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # User and session schemas use portable SQLAlchemy types. Scan and report
    # tables are created explicitly because production defaults include JSONB.
    User.__table__.metadata.create_all(
        engine,
        tables=[User.__table__, UserSession.__table__],
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE scans (
                id CHAR(32) NOT NULL PRIMARY KEY,
                website VARCHAR(2048) NOT NULL,
                framework VARCHAR(64) NOT NULL DEFAULT 'gdpr',
                user_id CHAR(32) NULL,
                lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
                compliance_status VARCHAR(32) NULL,
                total_checks INTEGER NOT NULL DEFAULT 0,
                passed_checks INTEGER NOT NULL DEFAULT 0,
                failed_checks INTEGER NOT NULL DEFAULT 0,
                observation_count INTEGER NOT NULL DEFAULT 0,
                risk_score FLOAT NULL,
                metadata JSON NOT NULL DEFAULT '{}',
                error_message TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at DATETIME NULL,
                completed_at DATETIME NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_scans_user_id_users FOREIGN KEY(user_id)
                    REFERENCES users(id) ON DELETE RESTRICT
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_scans_user_id_created_at ON scans(user_id, created_at)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE check_results (
                id CHAR(32) NOT NULL PRIMARY KEY,
                scan_id CHAR(32) NOT NULL,
                check_id VARCHAR(100) NOT NULL,
                name VARCHAR(300) NOT NULL,
                status VARCHAR(32) NOT NULL,
                severity VARCHAR(16) NOT NULL,
                confidence FLOAT NOT NULL,
                explanation TEXT NOT NULL,
                recommendation TEXT NULL,
                evidence JSON NOT NULL DEFAULT '[]',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_check_results_scan FOREIGN KEY(scan_id)
                    REFERENCES scans(id) ON DELETE CASCADE,
                CONSTRAINT uq_check_result_per_scan UNIQUE(scan_id, check_id)
            )
            """
        )

    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture()
def integration_environment(
    database_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[TestClient, RecordingTaskProducer, sessionmaker[Session]], None, None]:
    """Wire the actual auth/API services to isolated persistence and queue fakes."""

    def override_get_db() -> Generator[Session, None, None]:
        with database_factory() as session:
            yield session

    producer = RecordingTaskProducer()
    monkeypatch.setattr(
        auth_routes,
        "auth_service",
        AuthService(session_factory=database_factory),
    )
    monkeypatch.setattr(auth_routes, "rate_limiter", AllowAllRateLimiter())
    monkeypatch.setattr(
        scan_routes,
        "scan_service",
        AsyncScanService(
            session_factory=database_factory,
            task_producer=producer,
            framework_registry=FrameworkRegistry(
                {"gdpr": Path("rules/gdpr/rules.yaml")}
            ),
        ),
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        try:
            yield client, producer, database_factory
        finally:
            app.dependency_overrides.clear()


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token_response = client.get("/auth/csrf")
    assert token_response.status_code == 200
    return {
        "Origin": FRONTEND_ORIGIN,
        "X-CSRF-Token": token_response.json()["csrf_token"],
    }


def _register(client: TestClient, email: str) -> dict[str, Any]:
    response = client.post(
        "/auth/register",
        headers=_csrf_headers(client),
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    assert response.cookies.get("privacheck_session")
    return response.json()


def test_authenticated_scan_flow_enforces_owner_across_all_read_routes(
    integration_environment: tuple[
        TestClient, RecordingTaskProducer, sessionmaker[Session]
    ],
) -> None:
    client, producer, factory = integration_environment
    owner = _register(client, "owner.integration@example.com")

    accepted = client.post(
        "/scans",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "X-CSRF-Token": owner["csrf_token"],
        },
        json={"website": "https://example.com", "framework": "gdpr"},
    )
    assert accepted.status_code == 202, accepted.text
    scan_id = UUID(accepted.json()["scan_id"])

    # The real AsyncScanService persisted an owner and published a small task.
    with factory() as session:
        persisted_scan = ScanRepository.get_by_id(session, scan_id)
        assert persisted_scan is not None
        assert str(persisted_scan.user_id) == owner["user"]["id"]
        assert persisted_scan.lifecycle_status == "QUEUED"

    assert len(producer.messages) == 1
    task_name, task_options = producer.messages[0]
    assert task_name == "privacheck.crawler.execute_scan"
    task_payload = task_options["args"][0]
    assert task_payload["scan_id"] == str(scan_id)
    assert "password" not in str(task_payload).lower()
    assert "session" not in str(task_payload).lower()

    # Owner can list and inspect their queued scan.
    owner_history = client.get("/scans")
    assert owner_history.status_code == 200
    assert owner_history.headers["cache-control"] == "private, no-store"
    assert owner_history.json()["total"] == 1
    assert owner_history.json()["items"][0]["scan_id"] == str(scan_id)

    owner_status = client.get(f"/scans/{scan_id}")
    assert owner_status.status_code == 200
    assert owner_status.json()["lifecycle_status"] == "QUEUED"

    # A second real account must not learn that the scan exists.
    second_client = TestClient(app)
    try:
        _register(second_client, "other.integration@example.com")
        other_history = second_client.get("/scans")
        assert other_history.status_code == 200
        assert other_history.json()["total"] == 0
        assert second_client.get(f"/scans/{scan_id}").status_code == 404
        assert second_client.get(f"/scans/{scan_id}/report").status_code == 404

        # Complete the scan in persistence to exercise the report authorization
        # path after a report exists, rather than only the not-ready path.
        with factory() as session:
            with session.begin():
                ScanRepository.set_lifecycle_status(session, scan_id, "RUNNING")
                ScanRepository.update_report_summary(
                    session,
                    scan_id,
                    compliance_status="PASS",
                    total_checks=1,
                    passed_checks=1,
                    failed_checks=0,
                    observation_count=3,
                    risk_score=0.0,
                    report_metadata={
                        "risk_scoring_policy": {
                            "interpretation": "Integration test fixture only."
                        }
                    },
                )
                ScanRepository.set_lifecycle_status(session, scan_id, "COMPLETED")

        owner_report = client.get(f"/scans/{scan_id}/report")
        assert owner_report.status_code == 200, owner_report.text
        assert owner_report.headers["cache-control"] == "private, no-store"
        assert owner_report.json()["lifecycle_status"] == "COMPLETED"
        assert owner_report.json()["total_checks"] == 1
        assert owner_report.json()["results"] == []

        # The same foreign scan remains indistinguishable from a missing scan.
        foreign_report = second_client.get(f"/scans/{scan_id}/report")
        assert foreign_report.status_code == 404
        foreign_status = second_client.get(f"/scans/{scan_id}")
        assert foreign_status.status_code == 404
    finally:
        second_client.close()


def test_scan_api_rejects_anonymous_requests_and_missing_csrf(
    integration_environment: tuple[
        TestClient, RecordingTaskProducer, sessionmaker[Session]
    ],
) -> None:
    client, _producer, _factory = integration_environment
    payload = {"website": "https://example.com", "framework": "gdpr"}

    assert client.get("/scans").status_code == 401
    assert client.get(f"/scans/{UUID(int=1)}").status_code == 401
    assert client.get(f"/scans/{UUID(int=1)}/report").status_code == 401
    assert client.post("/scans", json=payload).status_code == 401

    user = _register(client, "csrf.integration@example.com")
    missing_csrf = client.post(
        "/scans",
        headers={"Origin": FRONTEND_ORIGIN},
        json=payload,
    )
    assert missing_csrf.status_code == 403

    untrusted_origin = client.post(
        "/scans",
        headers={
            "Origin": "https://attacker.invalid",
            "X-CSRF-Token": user["csrf_token"],
        },
        json=payload,
    )
    assert untrusted_origin.status_code == 403


def test_logout_revokes_session_for_protected_scan_endpoints(
    integration_environment: tuple[
        TestClient, RecordingTaskProducer, sessionmaker[Session]
    ],
) -> None:
    client, _producer, _factory = integration_environment
    user = _register(client, "logout.integration@example.com")
    assert client.get("/auth/me").status_code == 200

    logout_response = client.post(
        "/auth/logout",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "X-CSRF-Token": user["csrf_token"],
        },
    )
    assert logout_response.status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert client.get("/scans").status_code == 401
