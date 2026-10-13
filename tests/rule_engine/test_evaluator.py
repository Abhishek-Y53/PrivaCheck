from backend.domain.rules.models import (
    Rule,
    RuleCondition,
    RuleConditions,
    RuleResult,
    RuleSource,
)
from backend.rule_engine.evaluator import DeclarativeEvaluator
from backend.schemas.core import Observation


def make_rule(
    match: str = "all",
    condition_value: str = "https",
) -> Rule:
    """
    Create a generic test rule for the declarative evaluator.

    The rule checks the protocol field of network_request observations.
    """

    return Rule(
        id="TEST-EVAL-001",
        name="Test protocol rule",
        description="Generic evaluator test rule.",
        category="TEST",
        source=RuleSource(
            observation="network_request",
            match=match,
        ),
        evaluator="declarative",
        conditions=RuleConditions(
            all=[
                RuleCondition(
                    field="protocol",
                    operator="equals",
                    value=condition_value,
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


def observation(protocol: str) -> Observation:
    """
    Create a network_request observation with the supplied protocol.
    """

    return Observation(
        category="network_request",
        source_url="https://example.com",
        timestamp=1.0,
        data={
            "protocol": protocol,
        },
    )


def test_rule_passes_when_all_observations_match():
    rule = make_rule(
        match="all",
        condition_value="https",
    )

    observations = [
        observation("https"),
        observation("https"),
        observation("https"),
    ]

    result = DeclarativeEvaluator().evaluate(
        rule,
        observations,
    )

    assert result.passed is True
    assert len(result.matched_observations) == 3
    assert len(result.failed_observations) == 0


def test_rule_fails_when_one_observation_does_not_match():
    rule = make_rule(
        match="all",
        condition_value="https",
    )

    observations = [
        observation("https"),
        observation("http"),
        observation("https"),
    ]

    result = DeclarativeEvaluator().evaluate(
        rule,
        observations,
    )

    assert result.passed is False
    assert len(result.matched_observations) == 2
    assert len(result.failed_observations) == 1


def test_rule_passes_when_no_observation_matches():
    rule = make_rule(
        match="none",
        condition_value="http",
    )

    observations = [
        observation("https"),
        observation("https"),
    ]

    result = DeclarativeEvaluator().evaluate(
        rule,
        observations,
    )

    assert result.passed is True
    assert len(result.matched_observations) == 0
    assert len(result.failed_observations) == 2


def test_rule_fails_when_one_observation_matches_none():
    rule = make_rule(
        match="none",
        condition_value="http",
    )

    observations = [
        observation("https"),
        observation("http"),
        observation("https"),
    ]

    result = DeclarativeEvaluator().evaluate(
        rule,
        observations,
    )

    assert result.passed is False
    assert len(result.matched_observations) == 1
    assert len(result.failed_observations) == 2

    assert (
        result.matched_observations[0].data["protocol"]
        == "http"
    )


def test_none_match_fails_when_no_relevant_observations_exist():
    rule = make_rule(
        match="none",
        condition_value="http",
    )

    result = DeclarativeEvaluator().evaluate(
        rule,
        [],
    )

    assert result.passed is False
    assert len(result.matched_observations) == 0
    assert len(result.failed_observations) == 0