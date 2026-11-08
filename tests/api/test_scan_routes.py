from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.dependencies.auth import csrf_cookie_name, get_current_user
from backend.api.main import app
from backend.api.routes import scans
from backend.api.schemas import (
    ScanAcceptedResponse,
    ScanListResponse,
    ScanReportResponse,
    ScanStatusResponse,
)


class FakeScanService:
    def __init__(self):
        self.scan_id = uuid4()
        self.now = datetime.now(timezone.utc)
        self.calls = []

    async def submit_scan(self, request, *, user_id):
        self.calls.append(("submit", user_id))
        return ScanAcceptedResponse(
            scan_id=self.scan_id,
            lifecycle_status="QUEUED",
            website=request.website,
            framework=request.framework,
            created_at=self.now,
            task_id="task-123",
            status_url=f"/scans/{self.scan_id}",
            report_url=f"/scans/{self.scan_id}/report",
        )

    async def get_scan_status(self, scan_id, *, user_id):
        self.calls.append(("status", user_id))
        return ScanStatusResponse(
            scan_id=scan_id,
            website="https://example.com/",
            framework="gdpr",
            lifecycle_status="RUNNING",
            total_checks=0,
            passed_checks=0,
            failed_checks=0,
            observation_count=0,
            created_at=self.now,
        )

    async def list_scans(self, **kwargs):
        self.calls.append(("list", kwargs["user_id"]))
        return ScanListResponse(
            items=[], total=0, limit=kwargs["limit"], offset=kwargs["offset"]
        )

    async def get_scan_report(self, scan_id, *, user_id):
        self.calls.append(("report", user_id))
        return ScanReportResponse(
            scan_id=scan_id,
            website="https://example.com/",
            framework="gdpr",
            lifecycle_status="COMPLETED",
            compliance_status="PASS",
            total_checks=1,
            passed_checks=1,
            failed_checks=0,
            observation_count=5,
            risk_score=0.0,
            metadata={},
            results=[],
            created_at=self.now,
            started_at=self.now,
            completed_at=self.now,
        )


def _authenticated_client(user_id=None):
    user_id = user_id or uuid4()
    user = SimpleNamespace(id=user_id, email="owner@example.com", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    csrf = "test-csrf-token-with-enough-entropy-123456"
    client.cookies.set(csrf_cookie_name(), csrf)
    return client, user_id, {"X-CSRF-Token": csrf, "Origin": "http://127.0.0.1:5173"}


def _clear_overrides():
    app.dependency_overrides.clear()


def test_post_scan_returns_accepted_and_passes_authenticated_owner(monkeypatch):
    fake_service = FakeScanService()
    monkeypatch.setattr(scans, "scan_service", fake_service)
    client, user_id, headers = _authenticated_client()
    try:
        response = client.post(
            "/scans",
            json={"website": "https://example.com", "framework": "gdpr"},
            headers=headers,
        )
        assert response.status_code == 202
        assert response.headers["cache-control"] == "private, no-store"
        payload = response.json()
        assert payload["scan_id"] == str(fake_service.scan_id)
        assert payload["lifecycle_status"] == "QUEUED"
        assert payload["status_url"] == f"/scans/{fake_service.scan_id}"
        assert fake_service.calls == [("submit", user_id)]
    finally:
        _clear_overrides()


def test_scan_list_status_and_report_pass_authenticated_owner(monkeypatch):
    fake_service = FakeScanService()
    monkeypatch.setattr(scans, "scan_service", fake_service)
    client, user_id, _headers = _authenticated_client()
    try:
        status_response = client.get(f"/scans/{fake_service.scan_id}")
        list_response = client.get(
            "/scans?limit=10&offset=0&lifecycle_status=RUNNING"
        )
        report_response = client.get(f"/scans/{fake_service.scan_id}/report")

        assert status_response.status_code == 200
        assert status_response.headers["cache-control"] == "private, no-store"
        assert status_response.json()["lifecycle_status"] == "RUNNING"
        assert list_response.status_code == 200
        assert list_response.json()["items"] == []
        assert list_response.json()["limit"] == 10
        assert report_response.status_code == 200
        assert report_response.json()["lifecycle_status"] == "COMPLETED"
        assert fake_service.calls == [
            ("status", user_id),
            ("list", user_id),
            ("report", user_id),
        ]
    finally:
        _clear_overrides()


def test_all_scan_read_endpoints_require_authentication():
    client = TestClient(app)
    scan_id = uuid4()
    assert client.get("/scans").status_code == 401
    assert client.get(f"/scans/{scan_id}").status_code == 401
    assert client.get(f"/scans/{scan_id}/report").status_code == 401


def test_scan_creation_requires_authentication_and_csrf():
    client = TestClient(app)
    payload = {"website": "https://example.com", "framework": "gdpr"}
    assert client.post("/scans", json=payload).status_code == 401

    client, _user_id, _headers = _authenticated_client()
    try:
        response = client.post("/scans", json=payload)
        assert response.status_code == 403
    finally:
        _clear_overrides()
