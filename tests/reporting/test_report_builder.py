from backend.reporting.report_builder import (
    build_scan_report,
    calculate_risk_score,
    determine_overall_status,
    sanitize_check_result,
)
from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
    CrawlerResult,
    CrawlerStatus,
    Observation,
    SeverityLevel,
)


def make_check(check_id, status, severity=SeverityLevel.MEDIUM, evidence=None):
    return CheckResult(
        check_id=check_id,
        name=f"Rule {check_id}",
        status=status,
        severity=severity,
        confidence=0.8,
        explanation="Test result",
        recommendation="Review this result" if status != ComplianceStatus.PASS else None,
        evidence=evidence or [],
    )


def make_crawler_result(status=CrawlerStatus.COMPLETED, observations=None, error=None):
    return CrawlerResult(
        target_url="https://example.com/start?access_token=private-token#section",
        final_url="https://example.com/final?session=private-session#section",
        observations=observations or [],
        started_at=100.0,
        completed_at=102.5,
        status=status,
        error=error,
    )


def test_report_counts_and_overall_status_are_consistent():
    crawler = make_crawler_result()
    checks = [
        make_check("PASS-1", ComplianceStatus.PASS, SeverityLevel.HIGH),
        make_check("FAIL-1", ComplianceStatus.FAIL, SeverityLevel.MEDIUM),
        make_check("WARN-1", ComplianceStatus.WARNING, SeverityLevel.LOW),
    ]

    report = build_scan_report(crawler, checks, framework="gdpr", scan_id="scan-test")

    assert report.scan_id == "scan-test"
    assert report.target_url == "https://example.com/start"
    assert report.overall_status == ComplianceStatus.FAIL
    assert report.total_checks == 3
    assert report.passed_checks == 1
    assert report.failed_checks == 1
    assert len(report.issues) == 3
    assert report.risk_score == 44.44
    assert report.metadata["framework"] == "gdpr"
    assert report.metadata["observation_count"] == 0
    assert report.metadata["crawl_duration_seconds"] == 2.5
    assert report.metadata["result_counts"] == {"FAIL": 1, "PASS": 1, "WARNING": 1}


def test_report_redacts_cookie_storage_header_and_url_secrets():
    evidence = [
        Observation(
            category="cookie",
            source_url="https://example.com/?session=query-secret",
            timestamp=1.0,
            data={
                "name": "sessionid",
                "value": "cookie-secret",
                "url": "https://example.com/pixel?token=url-secret",
            },
        ),
        Observation(
            category="local_storage",
            source_url="https://example.com/",
            timestamp=1.1,
            data={"key": "tracker_id", "value": "storage-secret"},
        ),
        Observation(
            category="network_request",
            source_url="https://example.com/",
            timestamp=1.2,
            data={
                "url": "https://example.com/collect?access_token=request-secret",
                "headers": {
                    "Authorization": "Bearer header-secret",
                    "Cookie": "session=header-cookie-secret",
                    "Accept": "application/json",
                },
            },
        ),
    ]
    check = make_check("SEC-1", ComplianceStatus.WARNING, evidence=evidence)

    safe = sanitize_check_result(check)

    assert safe.evidence[0].data["value"] == "[REDACTED]"
    assert safe.evidence[0].source_url == "https://example.com/"
    assert safe.evidence[0].data["url"] == "https://example.com/pixel"
    assert safe.evidence[1].data["value"] == "[REDACTED]"
    assert safe.evidence[2].data["url"] == "https://example.com/collect"
    assert safe.evidence[2].data["headers"]["Authorization"] == "[REDACTED]"
    assert safe.evidence[2].data["headers"]["Cookie"] == "[REDACTED]"
    assert safe.evidence[2].data["headers"]["Accept"] == "application/json"

    # Report preparation must not mutate original evidence needed for local analysis.
    assert check.evidence[0].data["value"] == "cookie-secret"
    assert check.evidence[2].data["headers"]["Authorization"] == "Bearer header-secret"


def test_risk_score_is_bounded_and_severity_weighted():
    checks = [
        make_check("HIGH-FAIL", ComplianceStatus.FAIL, SeverityLevel.HIGH),
        make_check("LOW-PASS", ComplianceStatus.PASS, SeverityLevel.LOW),
    ]
    assert calculate_risk_score(checks) == 66.67
    assert calculate_risk_score([]) == 0.0


def test_failed_crawl_never_aggregates_to_pass():
    crawler = make_crawler_result(
        status=CrawlerStatus.FAILED,
        error="internal error details must not be included in report",
    )
    report = build_scan_report(
        crawler,
        [make_check("RULE-1", ComplianceStatus.PASS)],
        framework="gdpr",
    )

    assert report.overall_status == ComplianceStatus.MANUAL_REVIEW
    assert report.metadata["crawler_status"] == "FAILED"
    assert report.metadata["crawler_error_present"] is True
    assert "internal error details" not in str(report.model_dump())


def test_empty_results_are_manual_review_not_pass():
    crawler = make_crawler_result()
    assert determine_overall_status(crawler, []) == ComplianceStatus.MANUAL_REVIEW
