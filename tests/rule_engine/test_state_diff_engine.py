from backend.crawler.two_pass import PassSnapshot, TwoPassResult, ConsentInteractionResult
from backend.domain.rules.models import (
    Rule,
    RuleCondition,
    RuleConditions,
    RuleResult,
    RuleSource,
    StateDiffConfig,
)
from backend.rule_engine.engine import RuleEngine
from backend.schemas.core import CrawlerStatus, Observation


def make_rule() -> Rule:
    return Rule(
        id="TEST-SD-ENGINE-001",
        name="Reject state must not introduce a request",
        description="Generic state-diff engine integration test.",
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
        result=RuleResult(**{"pass": "PASS", "fail": "FAIL"}),
        state_diff=StateDiffConfig(
            key_fields=["url", "method"],
            assertion="reject_subset_of_accept",
        ),
        severity="HIGH",
    )


def obs(url: str) -> Observation:
    return Observation(
        category="network_request",
        source_url="https://example.com",
        timestamp=1.0,
        data={
            "url": url,
            "method": "GET",
            "resource_type": "script",
        },
    )


def make_snapshot(action, observations):
    return PassSnapshot(
        action=action,
        target_url="https://example.com",
        final_url="https://example.com",
        observations=observations,
        started_at=1.0,
        completed_at=2.0,
        status=CrawlerStatus.COMPLETED,
        interaction=ConsentInteractionResult(
        action=action,
        status="SUCCESS",
        matched_text=f"{action} all",
),
    )


def test_engine_evaluates_state_diff_result():
    result = RuleEngine().evaluate_rule(
        make_rule(),
        TwoPassResult(
            target_url="https://example.com",
            accept=make_snapshot("accept", [obs("https://cdn.example.com/a.js")]),
            reject=make_snapshot("reject", [obs("https://cdn.example.com/a.js")]),
            started_at=1.0,
            completed_at=2.0,
            status=CrawlerStatus.COMPLETED,
        ),
    )

    assert result.status.value == "PASS"
    assert len(result.evidence) == 2


def test_engine_rejects_plain_observations_for_state_diff_rule():
    try:
        RuleEngine().evaluate_rule(
            make_rule(),
            [obs("https://cdn.example.com/a.js")],
        )
    except TypeError as exc:
        assert "TwoPassResult" in str(exc)
    else:
        raise AssertionError("Expected TypeError for plain observations")
