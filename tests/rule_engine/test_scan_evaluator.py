from backend.domain.rules.models import Rule
from backend.rule_engine.scan_evaluator import evaluate_observations
from backend.schemas.core import CrawlerResult, CrawlerStatus, Observation


def make_rule(evaluator: str = "declarative") -> Rule:
    return Rule.model_validate(
        {
            "id": "TEST-EVAL-001",
            "name": "Privacy button exists",
            "description": "Test shared evaluator",
            "category": "TEST",
            "source": {"observation": "dom_button", "match": "any"},
            "evaluator": evaluator,
            "conditions": {
                "all": [
                    {"field": "text", "operator": "contains", "value": "privacy"}
                ]
            },
            "result": {"pass": "PASS", "fail": "FAIL"},
            "severity": "HIGH",
            "recommendation": "Review privacy controls",
        }
    )


def make_crawler_result(status: CrawlerStatus = CrawlerStatus.COMPLETED) -> CrawlerResult:
    return CrawlerResult(
        target_url="https://example.com/",
        final_url="https://example.com/",
        observations=[
            Observation(
                category="dom_button",
                source_url="https://example.com/",
                timestamp=10.0,
                data={"text": "privacy settings"},
            )
        ],
        started_at=10.0,
        completed_at=12.0,
        status=status,
    )


def test_shared_evaluator_runs_declarative_rule_and_builds_report():
    report = evaluate_observations(
        make_crawler_result(),
        [make_rule()],
        framework="gdpr",
        scan_id="00000000-0000-0000-0000-000000000001",
    )

    assert report.scan_id == "00000000-0000-0000-0000-000000000001"
    assert report.total_checks == 1
    assert report.passed_checks == 1
    assert report.issues[0].status.value == "PASS"
    assert report.metadata["framework"] == "gdpr"


def test_state_diff_without_two_pass_result_is_manual_review():
    report = evaluate_observations(
        make_crawler_result(),
        [make_rule("state_diff")],
        framework="gdpr",
    )

    assert report.issues[0].status.value == "MANUAL_REVIEW"
    assert report.overall_status.value == "MANUAL_REVIEW"
    assert report.failed_checks == 0


def test_unsupported_evaluator_is_manual_review_not_pass():
    report = evaluate_observations(
        make_crawler_result(),
        [make_rule("visual")],
        framework="gdpr",
    )

    assert report.issues[0].status.value == "MANUAL_REVIEW"
    assert report.overall_status.value == "MANUAL_REVIEW"


def test_failed_crawler_never_produces_ordinary_pass_or_fail():
    report = evaluate_observations(
        make_crawler_result(CrawlerStatus.FAILED),
        [make_rule()],
        framework="gdpr",
    )

    assert report.issues[0].status.value == "MANUAL_REVIEW"
    assert report.overall_status.value == "MANUAL_REVIEW"
