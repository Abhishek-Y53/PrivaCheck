import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.api.schemas import ScanRequest
from backend.api.services.async_scan_service import (
    AsyncScanService,
    ScanEnqueueError,
    UnsupportedFrameworkError,
)
from backend.infrastructure.database.repositories import ScanRepository
from backend.rule_engine.framework_registry import FrameworkRegistry


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return nullcontext()


class FakeProducer:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def send_task(self, task_name, **kwargs):
        self.calls.append((task_name, kwargs))
        if self.fail:
            raise ConnectionError("broker unavailable")
        return SimpleNamespace(id=kwargs["task_id"])


def test_submit_scan_persists_record_and_publishes_small_contract(monkeypatch):
    scan_id = uuid4()
    created_at = datetime.now(timezone.utc)
    created = []
    user_id = uuid4()

    def create_scan(session, *, website, framework, user_id):
        created.append((website, framework, user_id))
        return SimpleNamespace(id=scan_id, created_at=created_at)

    monkeypatch.setattr(ScanRepository, "create", staticmethod(create_scan))
    producer = FakeProducer()
    service = AsyncScanService(
        session_factory=FakeSession,
        task_producer=producer,
        framework_registry=FrameworkRegistry({"gdpr": Path("rules/gdpr/rules.yaml")}),
    )

    response = asyncio.run(
        service.submit_scan(
            ScanRequest(website="https://example.com", framework=" GDPR "),
            user_id=user_id,
        )
    )

    assert response.scan_id == scan_id
    assert response.lifecycle_status == "QUEUED"
    assert response.framework == "gdpr"
    assert created == [("https://example.com", "gdpr", user_id)]
    assert len(producer.calls) == 1
    task_name, options = producer.calls[0]
    assert task_name == "privacheck.crawler.execute_scan"
    assert options["queue"] == "crawler.scan"
    assert options["args"][0]["message_type"] == "crawler.scan.requested"
    assert options["args"][0]["scan_id"] == str(scan_id)
    assert "observations" not in options["args"][0]


def test_unsupported_framework_is_rejected_before_scan_creation(monkeypatch):
    monkeypatch.setattr(
        ScanRepository,
        "create",
        staticmethod(lambda *args, **kwargs: pytest.fail("must not create scan")),
    )
    service = AsyncScanService(
        session_factory=FakeSession,
        task_producer=FakeProducer(),
        framework_registry=FrameworkRegistry({"gdpr": Path("rules/gdpr/rules.yaml")}),
    )

    with pytest.raises(UnsupportedFrameworkError):
        asyncio.run(
            service.submit_scan(
                ScanRequest(website="https://example.com", framework="hipaa"),
                user_id=uuid4(),
            )
        )


def test_broker_failure_marks_queued_scan_failed(monkeypatch):
    scan_id = uuid4()
    created_at = datetime.now(timezone.utc)
    transitions = []

    monkeypatch.setattr(
        ScanRepository,
        "create",
        staticmethod(lambda *args, **kwargs: SimpleNamespace(id=scan_id, created_at=created_at)),
    )
    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_update",
        staticmethod(lambda session, requested_id: SimpleNamespace(lifecycle_status="QUEUED")),
    )
    monkeypatch.setattr(
        ScanRepository,
        "set_lifecycle_status",
        staticmethod(lambda session, requested_id, new_status, **kwargs: transitions.append((new_status, kwargs))),
    )

    service = AsyncScanService(
        session_factory=FakeSession,
        task_producer=FakeProducer(fail=True),
        framework_registry=FrameworkRegistry({"gdpr": Path("rules/gdpr/rules.yaml")}),
    )

    with pytest.raises(ScanEnqueueError) as exc_info:
        asyncio.run(
            service.submit_scan(
                ScanRequest(website="https://example.com"), user_id=uuid4()
            )
        )

    assert exc_info.value.scan_id == scan_id
    assert transitions[0][0] == "FAILED"
    assert "could not be submitted" in transitions[0][1]["error_message"]


def test_scan_status_lookup_is_scoped_to_authenticated_user(monkeypatch):
    from backend.api.services.async_scan_service import ScanNotFoundError

    scan_id = uuid4()
    user_id = uuid4()
    looked_up = []
    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_user",
        staticmethod(lambda session, requested_scan_id, requested_user_id: (
            looked_up.append((requested_scan_id, requested_user_id)) or None
        )),
    )
    service = AsyncScanService(session_factory=FakeSession, task_producer=FakeProducer())

    with pytest.raises(ScanNotFoundError):
        asyncio.run(service.get_scan_status(scan_id, user_id=user_id))

    assert looked_up == [(scan_id, user_id)]


def test_scan_report_lookup_is_scoped_to_authenticated_user(monkeypatch):
    from backend.api.services.async_scan_service import ScanNotFoundError

    scan_id = uuid4()
    user_id = uuid4()
    looked_up = []
    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_user",
        staticmethod(lambda session, requested_scan_id, requested_user_id: (
            looked_up.append((requested_scan_id, requested_user_id)) or None
        )),
    )
    service = AsyncScanService(session_factory=FakeSession, task_producer=FakeProducer())

    with pytest.raises(ScanNotFoundError):
        asyncio.run(service.get_scan_report(scan_id, user_id=user_id))

    assert looked_up == [(scan_id, user_id)]


def test_scan_history_count_and_rows_are_scoped_to_authenticated_user(monkeypatch):
    user_id = uuid4()
    list_owners = []

    class ListingSession(FakeSession):
        def scalar(self, statement):
            sql = str(statement.compile())
            assert "scans.user_id" in sql
            return 0

    monkeypatch.setattr(
        ScanRepository,
        "list_recent",
        staticmethod(lambda session, **kwargs: (
            list_owners.append(kwargs["user_id"]) or []
        )),
    )
    service = AsyncScanService(session_factory=ListingSession, task_producer=FakeProducer())

    response = asyncio.run(service.list_scans(user_id=user_id))

    assert response.items == []
    assert response.total == 0
    assert list_owners == [user_id]


def test_scan_creation_rejects_missing_owner_before_persistence(monkeypatch):
    monkeypatch.setattr(
        ScanRepository,
        "create",
        staticmethod(lambda *args, **kwargs: pytest.fail("must not create ownerless scan")),
    )
    service = AsyncScanService(session_factory=FakeSession, task_producer=FakeProducer())

    with pytest.raises(ValueError, match="authenticated UUID user_id is required"):
        asyncio.run(
            service.submit_scan(
                ScanRequest(website="https://example.com"), user_id=None
            )
        )
