from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.domain.rules.models import Rule
from backend.infrastructure.database.repositories import (
    CheckResultRepository,
    ObservationRepository,
    ScanRepository,
)
from backend.rule_engine.framework_registry import FrameworkRegistry
from backend.services.compliance_service.evaluation_service import (
    ComplianceEvaluationService,
    EvaluationRejected,
    reconstruct_crawler_result,
)
from backend.contracts.task_messages import ComplianceEvaluationRequested


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return nullcontext()


class FakeRuleLoader:
    def __init__(self, rules):
        self.rules = rules
        self.path = None

    def load(self, path):
        self.path = path
        return self.rules


def make_rule():
    return Rule.model_validate(
        {
            "id": "ASYNC-001",
            "name": "Privacy control exists",
            "description": "Test async evaluator",
            "category": "TEST",
            "source": {"observation": "dom_button", "match": "any"},
            "evaluator": "declarative",
            "conditions": {
                "all": [
                    {"field": "text", "operator": "contains", "value": "privacy"}
                ]
            },
            "result": {"pass": "PASS", "fail": "FAIL"},
            "severity": "HIGH",
            "recommendation": "Review the privacy control",
        }
    )


def make_rows(now):
    return [
        SimpleNamespace(
            category="dom_button",
            source_url="https://example.com/",
            observed_at=now,
            data={"text": "privacy settings"},
        ),
        SimpleNamespace(
            category="page_context",
            source_url="https://example.com/",
            observed_at=now,
            data={"final_url": "https://www.example.com/"},
        ),
    ]


def test_reconstruct_crawler_result_uses_page_context_final_url():
    now = datetime.now(timezone.utc)
    rows = make_rows(now)

    result = reconstruct_crawler_result(
        website="https://example.com/",
        started_at=now,
        created_at=now,
        occurred_at=now,
        observation_rows=rows,
    )

    assert result.target_url == "https://example.com/"
    assert result.final_url == "https://www.example.com/"
    assert result.status.value == "COMPLETED"
    assert len(result.observations) == 2


def test_reconstruct_rejects_non_mapping_observation_payload():
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        category="dom_button",
        source_url="https://example.com/",
        observed_at=now,
        data=["not", "a", "mapping"],
    )

    with pytest.raises(EvaluationRejected) as error:
        reconstruct_crawler_result(
            website="https://example.com/",
            started_at=now,
            created_at=now,
            occurred_at=now,
            observation_rows=[row],
        )

    assert error.value.failure_code == "OBSERVATIONS_UNAVAILABLE"


def test_service_evaluates_and_persists_atomically(monkeypatch):
    scan_id = uuid4()
    now = datetime.now(timezone.utc)
    rows = make_rows(now)
    scan = SimpleNamespace(
        id=scan_id,
        website="https://example.com/",
        framework="gdpr",
        lifecycle_status="RUNNING",
        started_at=now,
        created_at=now,
        compliance_status=None,
        total_checks=0,
        passed_checks=0,
        failed_checks=0,
        observation_count=0,
        risk_score=None,
        report_metadata={},
    )
    events = []

    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_update",
        staticmethod(lambda session, requested_id: scan),
    )
    monkeypatch.setattr(
        ObservationRepository,
        "list_for_scan",
        staticmethod(lambda session, requested_id: rows),
    )
    monkeypatch.setattr(
        ObservationRepository,
        "count_for_scan",
        staticmethod(lambda session, requested_id: len(rows)),
    )
    monkeypatch.setattr(
        CheckResultRepository,
        "replace_for_scan",
        staticmethod(lambda session, requested_id, results: events.append(("replace", len(results)))),
    )

    def update_summary(session, requested_id, **values):
        events.append(("summary", values["total_checks"]))
        for key, value in values.items():
            setattr(scan, key, value)
        return scan

    def set_status(session, requested_id, status, **kwargs):
        events.append(("status", status))
        scan.lifecycle_status = status
        return scan

    def delete_observations(session, requested_id):
        events.append(("delete_observations", requested_id))
        return len(rows)

    monkeypatch.setattr(ScanRepository, "update_report_summary", staticmethod(update_summary))
    monkeypatch.setattr(ScanRepository, "set_lifecycle_status", staticmethod(set_status))
    monkeypatch.setattr(
        ObservationRepository,
        "delete_for_scan",
        staticmethod(delete_observations),
    )

    loader = FakeRuleLoader([make_rule()])
    service = ComplianceEvaluationService(
        session_factory=FakeSession,
        rule_loader=loader,
        framework_registry=FrameworkRegistry({"gdpr": Path("rules/gdpr/rules.yaml")}),
    )
    message = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id="gdpr",
        observation_count=len(rows),
    )

    outcome = service.evaluate(message)

    assert outcome.status == "completed"
    assert outcome.result_count == 1
    assert outcome.compliance_status == "PASS"
    assert scan.lifecycle_status == "COMPLETED"
    assert scan.total_checks == 1
    assert events == [
        ("replace", 1),
        ("summary", 1),
        ("delete_observations", scan_id),
        ("status", "COMPLETED"),
    ]
    assert loader.path == Path("rules/gdpr/rules.yaml")


def test_duplicate_delivery_after_completion_is_skipped_without_writes(monkeypatch):
    scan_id = uuid4()
    now = datetime.now(timezone.utc)
    scan = SimpleNamespace(
        id=scan_id,
        website="https://example.com/",
        framework="gdpr",
        lifecycle_status="COMPLETED",
        started_at=now,
        created_at=now,
    )
    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_update",
        staticmethod(lambda session, requested_id: scan),
    )
    monkeypatch.setattr(
        CheckResultRepository,
        "replace_for_scan",
        staticmethod(lambda *args, **kwargs: pytest.fail("completed scan must not be rewritten")),
    )

    service = ComplianceEvaluationService(session_factory=FakeSession)
    message = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id="gdpr",
        observation_count=2,
    )

    outcome = service.evaluate(message)

    assert outcome.status == "skipped"
    assert outcome.reason == "scan_is_terminal"


def test_observation_count_mismatch_is_rejected(monkeypatch):
    scan_id = uuid4()
    now = datetime.now(timezone.utc)
    rows = make_rows(now)
    scan = SimpleNamespace(
        id=scan_id,
        website="https://example.com/",
        framework="gdpr",
        lifecycle_status="RUNNING",
        started_at=now,
        created_at=now,
    )
    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_update",
        staticmethod(lambda session, requested_id: scan),
    )
    monkeypatch.setattr(
        ObservationRepository,
        "list_for_scan",
        staticmethod(lambda session, requested_id: rows),
    )

    service = ComplianceEvaluationService(session_factory=FakeSession)
    message = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id="gdpr",
        observation_count=99,
    )

    with pytest.raises(EvaluationRejected) as error:
        service.evaluate(message)

    assert error.value.failure_code == "OBSERVATIONS_UNAVAILABLE"


def test_duplicate_that_finishes_after_another_worker_is_a_noop(monkeypatch):
    scan_id = uuid4()
    now = datetime.now(timezone.utc)
    rows = make_rows(now)
    scan = SimpleNamespace(
        id=scan_id,
        website="https://example.com/",
        framework="gdpr",
        lifecycle_status="RUNNING",
        started_at=now,
        created_at=now,
    )
    lock_calls = {"count": 0}

    def get_locked_scan(session, requested_id):
        lock_calls["count"] += 1
        if lock_calls["count"] == 2:
            scan.lifecycle_status = "COMPLETED"
        return scan

    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_update",
        staticmethod(get_locked_scan),
    )
    monkeypatch.setattr(
        ObservationRepository,
        "list_for_scan",
        staticmethod(lambda session, requested_id: rows),
    )
    monkeypatch.setattr(
        CheckResultRepository,
        "replace_for_scan",
        staticmethod(lambda *args, **kwargs: pytest.fail("duplicate must not replace findings")),
    )

    service = ComplianceEvaluationService(
        session_factory=FakeSession,
        rule_loader=FakeRuleLoader([make_rule()]),
        framework_registry=FrameworkRegistry({"gdpr": Path("rules/gdpr/rules.yaml")}),
    )
    message = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id="gdpr",
        observation_count=len(rows),
    )

    outcome = service.evaluate(message)

    assert outcome.status == "skipped"
    assert outcome.reason == "scan_became_terminal_during_evaluation"
    assert lock_calls["count"] == 2


def test_unsupported_framework_is_rejected_before_rule_loading(monkeypatch):
    scan_id = uuid4()
    now = datetime.now(timezone.utc)
    scan = SimpleNamespace(
        id=scan_id,
        website="https://example.com/",
        framework="unknown",
        lifecycle_status="RUNNING",
        started_at=now,
        created_at=now,
    )
    monkeypatch.setattr(
        ScanRepository,
        "get_by_id_for_update",
        staticmethod(lambda session, requested_id: scan),
    )
    loader = FakeRuleLoader([make_rule()])
    service = ComplianceEvaluationService(
        session_factory=FakeSession,
        rule_loader=loader,
    )
    message = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id="unknown",
        observation_count=1,
    )

    with pytest.raises(EvaluationRejected) as error:
        service.evaluate(message)

    assert error.value.failure_code == "UNSUPPORTED_FRAMEWORK"
    assert loader.path is None
