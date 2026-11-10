"""New scans must evaluate their own pinned immutable version, not current YAML."""
from __future__ import annotations

import hashlib
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.contracts.task_messages import ComplianceEvaluationRequested
from backend.infrastructure.database.repositories import ObservationRepository, ScanRepository
from backend.services.compliance_service.evaluation_service import (
    ComplianceEvaluationService, EvaluationOutcome, EvaluationRejected,
)

CONTENT = '''rules:
  - id: CUSTOM-001
    name: Privacy button
    description: Simple test
    category: PRIVACY
    source: {observation: dom_button, match: any}
    evaluator: declarative
    conditions:
      any:
        - {field: text, operator: contains, value: privacy}
    result: {pass: PASS, fail: FAIL}
    severity: MEDIUM
'''


class FakeSession:
    def __init__(self, ruleset):
        self.ruleset = ruleset

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def begin(self): return nullcontext()
    def get(self, model, key): return self.ruleset if self.ruleset.id == key else None


@pytest.fixture
def pinned(monkeypatch):
    version_id, scan_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    scan = SimpleNamespace(
        id=scan_id, ruleset_version_id=version_id, framework='custom', lifecycle_status='RUNNING',
        website='https://example.com/', started_at=now, created_at=now,
    )
    version = SimpleNamespace(
        id=version_id, status='PUBLISHED', framework_slug='custom', yaml_content=CONTENT,
        sha256=hashlib.sha256(CONTENT.encode()).hexdigest(),
    )
    observations = [SimpleNamespace(category='dom_button', source_url='https://example.com/',
                                    observed_at=now, data={'text':'privacy settings'})]
    monkeypatch.setattr(ScanRepository, 'get_by_id_for_update', staticmethod(lambda s, x: scan))
    monkeypatch.setattr(ObservationRepository, 'list_for_scan', staticmethod(lambda s, x: observations))
    service = ComplianceEvaluationService(session_factory=lambda: FakeSession(version))
    message = ComplianceEvaluationRequested(scan_id=scan_id, framework_id='custom',
                                            ruleset_version_id=version_id, observation_count=1)
    return service, message, version


def test_uses_pinned_content_and_not_filesystem_registry(pinned, monkeypatch):
    service, message, version = pinned
    def persist(message, report, observation_count):
        assert report.total_checks == 1
        assert report.issues[0].check_id == 'CUSTOM-001'
        assert observation_count == 1
        return EvaluationOutcome(status='completed', scan_id=str(message.scan_id), result_count=1)
    monkeypatch.setattr(service, '_persist_report', persist)
    outcome = service.evaluate(message)
    assert outcome.result_count == 1


def test_rejects_broker_version_mismatch(pinned):
    service, message, version = pinned
    wrong = message.model_copy(update={'ruleset_version_id': uuid4()})
    with pytest.raises(EvaluationRejected) as error:
        service.evaluate(wrong)
    assert error.value.failure_code == 'UNSUPPORTED_FRAMEWORK'


def test_rejects_tampered_published_yaml(pinned):
    service, message, version = pinned
    version.yaml_content += '\n# tampered'
    with pytest.raises(EvaluationRejected) as error:
        service.evaluate(message)
    assert error.value.failure_code == 'RULE_LOAD_FAILED'
