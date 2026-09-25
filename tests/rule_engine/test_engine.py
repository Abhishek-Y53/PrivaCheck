from backend.domain.rules.models import (
    Rule,
    RuleConditions,
    RuleCondition,
    RuleResult,
    RuleSource,
)

from backend.rule_engine.engine import RuleEngine
from backend.schemas.core import (
    Observation,
    SeverityLevel,
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
        recommendation="Use HTTPS for all requests.",
    )


def test_engine_returns_pass():

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

    engine = RuleEngine()

    result = engine.evaluate_rule(
        create_rule(),
        observations,
    )

    assert result.check_id == "TEST-001"
    assert result.status.value == "PASS"
    assert len(result.evidence) == 2


def test_engine_returns_fail():

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

    engine = RuleEngine()

    result = engine.evaluate_rule(
        create_rule(),
        observations,
    )

    assert result.check_id == "TEST-001"
    assert result.status.value == "FAIL"
    assert len(result.evidence) == 1
    assert result.evidence[0].data["protocol"] == "http"