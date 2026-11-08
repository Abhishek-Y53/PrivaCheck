from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.contracts.task_messages import (
    ComplianceEvaluationCompleted,
    ComplianceEvaluationFailed,
    ComplianceEvaluationRequested,
    CrawlerScanCompleted,
    CrawlerScanFailed,
    CrawlerScanRequested,
    parse_task_message,
)


def test_crawler_requested_json_round_trip():
    message = CrawlerScanRequested(
        scan_id=uuid4(),
        target_url="https://example.com/",
        timeout_seconds=120,
    )
    payload = message.to_payload()

    assert payload["schema_version"] == 1
    assert payload["message_type"] == "crawler.scan.requested"
    assert isinstance(payload["scan_id"], str)
    assert isinstance(payload["occurred_at"], str)

    parsed = parse_task_message(payload)
    assert isinstance(parsed, CrawlerScanRequested)
    assert parsed.scan_id == message.scan_id
    assert parsed.target_url == message.target_url


def test_crawler_completed_contract():
    message = CrawlerScanCompleted(scan_id=uuid4(), observation_count=17)
    assert isinstance(parse_task_message(message.to_payload()), CrawlerScanCompleted)


def test_crawler_failed_contract_rejects_free_form_error_text():
    message = CrawlerScanFailed(
        scan_id=uuid4(), failure_code="NAVIGATION_FAILED", retryable=True
    )
    payload = message.to_payload()
    payload["error"] = "raw exception with possible secrets"
    with pytest.raises(ValidationError):
        parse_task_message(payload)


def test_compliance_requested_contract():
    message = ComplianceEvaluationRequested(
        scan_id=uuid4(), framework_id="gdpr", observation_count=25
    )
    assert isinstance(
        parse_task_message(message.to_payload()), ComplianceEvaluationRequested
    )


def test_compliance_completed_contract():
    message = ComplianceEvaluationCompleted(
        scan_id=uuid4(),
        result_count=42,
        compliance_status="FAIL",
        risk_score=48.84,
    )
    assert isinstance(
        parse_task_message(message.to_payload()), ComplianceEvaluationCompleted
    )


def test_compliance_failed_contract():
    message = ComplianceEvaluationFailed(
        scan_id=uuid4(), failure_code="RULE_LOAD_FAILED", retryable=False
    )
    assert isinstance(
        parse_task_message(message.to_payload()), ComplianceEvaluationFailed
    )


def test_rejects_unsupported_schema_version():
    payload = CrawlerScanCompleted(scan_id=uuid4(), observation_count=0).to_payload()
    payload["schema_version"] = 2
    with pytest.raises(ValidationError):
        parse_task_message(payload)


def test_rejects_unknown_message_type():
    payload = CrawlerScanCompleted(scan_id=uuid4(), observation_count=0).to_payload()
    payload["message_type"] = "crawler.scan.completed.v2"
    with pytest.raises(ValidationError):
        parse_task_message(payload)


def test_rejects_invalid_target_url():
    with pytest.raises(ValidationError):
        CrawlerScanRequested(scan_id=uuid4(), target_url="file:///etc/passwd")


def test_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        CrawlerScanCompleted(
            scan_id=uuid4(),
            observation_count=0,
            occurred_at=datetime(2026, 11, 3, 12, 0, 0),
        )


def test_rejects_invalid_compliance_status_and_score():
    with pytest.raises(ValidationError):
        ComplianceEvaluationCompleted(
            scan_id=uuid4(),
            result_count=2,
            compliance_status="UNKNOWN",
            risk_score=120,
        )
