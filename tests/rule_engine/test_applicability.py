from backend.domain.rules.models import (
    Rule,
    RuleApplicability,
    RuleCondition,
    RuleConditions,
    RuleResult,
    RuleSource,
)
from backend.rule_engine.engine import RuleEngine
from backend.schemas.core import (
    ComplianceStatus,
    Observation,
)


def make_rule() -> Rule:
    return Rule(
        id="TEST-APP-001",
        name="Reject All consent option",
        description="Test applicability handling.",
        category="CONSENT",
        applicability=RuleApplicability(
            observation="dom_button",
            conditions=RuleConditions(
                any=[
                    RuleCondition(
                        field="text",
                        operator="matches",
                        value=(
                            "(?i)accept all cookies|"
                            "reject all cookies|"
                            "cookie settings"
                        ),
                    )
                ]
            ),
        ),
        source=RuleSource(
            observation="dom_button",
            match="any",
        ),
        evaluator="declarative",
        conditions=RuleConditions(
            any=[
                RuleCondition(
                    field="text",
                    operator="matches",
                    value="(?i)reject all",
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


def observation(text: str) -> Observation:
    return Observation(
        category="dom_button",
        source_url="https://example.com",
        timestamp=1.0,
        data={
            "text": text,
            "aria_label": None,
        },
    )


def test_rule_is_not_applicable_without_consent_mechanism():
    result = RuleEngine().evaluate_rule(
        make_rule(),
        [
            observation("Login"),
            observation("Submit"),
            observation("Contact Us"),
        ],
    )

    assert result.status == ComplianceStatus.NOT_APPLICABLE


def test_rule_fails_when_consent_exists_but_reject_all_is_missing():
    result = RuleEngine().evaluate_rule(
        make_rule(),
        [
            observation("Accept All Cookies"),
            observation("Manage Cookie Preferences"),
        ],
    )

    assert result.status == ComplianceStatus.FAIL


def test_rule_passes_when_consent_and_reject_all_exist():
    result = RuleEngine().evaluate_rule(
        make_rule(),
        [
            observation("Accept All Cookies"),
            observation("Reject All Cookies"),
        ],
    )

    assert result.status == ComplianceStatus.PASS