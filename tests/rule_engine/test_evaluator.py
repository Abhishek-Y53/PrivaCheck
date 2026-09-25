from backend.domain.rules.models import (
    Rule,
    RuleConditions,
    RuleCondition,
    RuleResult,
    RuleSource,
)

from backend.rule_engine.evaluator import DeclarativeEvaluator
from backend.schemas.core import (
    Observation,
    SeverityLevel,
    ComplianceStatus,
)


def create_rule():
    return Rule(
        id="TEST-001",
        name="HTTPS is required",
        description="All requests must use HTTPS.",
        category="SECURITY",
        source=RuleSource(
            observation="network_request",
            match="all",
        ),
        evaluator="declarative",
        conditions=RuleConditions(
            all=[
                RuleCondition(
                    field="protocol",
                    operator="equals",
                    value="https",
                )
            ]
        ),
        result=RuleResult(
            **{
                "pass": "PASS",
                "fail": "FAIL",
            }
        ),
        severity=SeverityLevel.HIGH,
    )


def test_rule_passes_when_all_observations_match():

    observations = [
        Observation(
            category="network_request",
            source_url="https://example.com",
            timestamp=1.0,
            data={"protocol": "https"},
        ),
        Observation(
            category="network_request",
            source_url="https://example.com",
            timestamp=2.0,
            data={"protocol": "https"},
        ),
    ]

    evaluator = DeclarativeEvaluator()
    result = evaluator.evaluate(create_rule(), observations)

    assert result.passed is True
    assert len(result.matched_observations) == 2
    assert len(result.failed_observations) == 0


def test_rule_fails_when_one_observation_does_not_match():

    observations = [
        Observation(
            category="network_request",
            source_url="https://example.com",
            timestamp=1.0,
            data={"protocol": "https"},
        ),
        Observation(
            category="network_request",
            source_url="https://example.com",
            timestamp=2.0,
            data={"protocol": "http"},
        ),
    ]

    evaluator = DeclarativeEvaluator()
    result = evaluator.evaluate(create_rule(), observations)

    assert result.passed is False
    assert len(result.matched_observations) == 1
    assert len(result.failed_observations) == 1