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
def test_engine_does_not_use_non_matching_candidates_as_evidence_for_any_match():
    rule = create_rule()

    rule.source.match = "any"

    observations = [
        Observation(
            category="network_request",
            source_url="https://example.com",
            timestamp=1.0,
            data={"protocol": "http"},
        ),
        Observation(
            category="network_request",
            source_url="https://example.com",
            timestamp=2.0,
            data={"protocol": "ftp"},
        ),
    ]

    engine = RuleEngine()

    result = engine.evaluate_rule(
        rule,
        observations,
    )

    assert result.status.value == "FAIL"
    assert result.evidence == []

def test_engine_returns_offending_evidence_for_none_match_rule():
    rule = Rule(
        id="TEST-NONE-ENGINE-001",
        name="No HTTP requests",
        description="Fails when an HTTP request exists.",
        category="TEST",
        source=RuleSource(
            observation="network_request",
            match="none",
        ),
        evaluator="declarative",
        conditions=RuleConditions(
            all=[
                RuleCondition(
                    field="protocol",
                    operator="equals",
                    value="http",
                )
            ]
        ),
        result=RuleResult(
            **{
                "pass": "PASS",
                "fail": "FAIL",
            }
        ),
        severity="HIGH",
    )

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

    result = RuleEngine().evaluate_rule(
        rule,
        observations,
    )

    assert result.status.value == "FAIL"
    assert len(result.evidence) == 1
    assert result.evidence[0].data["protocol"] == "http"