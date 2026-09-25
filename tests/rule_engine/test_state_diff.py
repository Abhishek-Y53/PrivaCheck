from backend.domain.rules.models import (
    Rule,
    RuleCondition,
    RuleConditions,
    RuleResult,
    RuleSource,
    StateDiffConfig,
)
from backend.rule_engine.evaluators.state_diff import StateDiffEvaluator
from backend.schemas.core import Observation


def make_rule(assertion: str = "reject_subset_of_accept") -> Rule:
    return Rule(
        id="TEST-SD-001",
        name="Reject state must be a subset of Accept state",
        description="Generic state comparison rule.",
        category="TEST",
        source=RuleSource(
            observation="network_request",
            match="all",
        ),
        evaluator="state_diff",
        conditions=RuleConditions(
            all=[
                RuleCondition(
                    field="resource_type",
                    operator="equals",
                    value="script",
                )
            ]
        ),
        result=RuleResult(
            **{
                "pass": "PASS",
                "fail": "FAIL",
            }
        ),
        state_diff=StateDiffConfig(
            key_fields=["url", "method"],
            assertion=assertion,
        ),
        severity="HIGH",
    )


def observation(url: str, resource_type: str = "script") -> Observation:
    return Observation(
        category="network_request",
        source_url="https://example.com",
        timestamp=1.0,
        data={
            "url": url,
            "method": "GET",
            "resource_type": resource_type,
        },
    )


def test_reject_subset_of_accept_passes_when_reject_has_no_extra_observation():
    evaluator = StateDiffEvaluator()
    rule = make_rule()

    accept = [
        observation("https://cdn.example.com/a.js"),
        observation("https://cdn.example.com/b.js"),
    ]
    reject = [
        observation("https://cdn.example.com/a.js"),
    ]

    result = evaluator.evaluate(rule, accept, reject)

    assert result.passed is True
    assert result.accept_only_count == 1
    assert result.reject_only_count == 0
    assert result.common_count == 1


def test_reject_subset_of_accept_fails_when_reject_has_extra_observation():
    evaluator = StateDiffEvaluator()
    rule = make_rule()

    accept = [
        observation("https://cdn.example.com/a.js"),
    ]
    reject = [
        observation("https://cdn.example.com/a.js"),
        observation("https://tracker.example.com/track.js"),
    ]

    result = evaluator.evaluate(rule, accept, reject)

    assert result.passed is False
    assert result.accept_only_count == 0
    assert result.reject_only_count == 1
    assert len(result.failed_observations) == 1
    assert result.failed_observations[0].data["url"] == "https://tracker.example.com/track.js"


def test_conditions_filter_observations_before_diff():
    evaluator = StateDiffEvaluator()
    rule = make_rule()

    accept = [
        observation("https://cdn.example.com/a.js", resource_type="script"),
    ]
    reject = [
        observation("https://cdn.example.com/a.js", resource_type="image"),
        observation("https://cdn.example.com/a.js", resource_type="script"),
    ]

    result = evaluator.evaluate(rule, accept, reject)

    assert result.passed is True
    assert result.reject_only_count == 0
    assert result.common_count == 1
