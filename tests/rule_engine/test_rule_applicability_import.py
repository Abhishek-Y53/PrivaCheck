from backend.domain.rules.models import Rule, RuleApplicability


def test_rule_applicability_is_resolved_and_validated() -> None:
    rule = Rule.model_validate(
        {
            "id": "TEST-APP-001",
            "name": "Applicability import regression",
            "description": "Ensures RuleApplicability is available when Rule is defined.",
            "category": "CONSENT",
            "source": {"observation": "dom_button"},
            "evaluator": "declarative",
            "conditions": {},
            "result": {"pass": "PASS", "fail": "FAIL"},
            "applicability": {
                "observation": "dom_button",
                "conditions": {
                    "all": [
                        {
                            "field": "text",
                            "operator": "contains",
                            "value": "reject",
                        }
                    ]
                },
            },
            "severity": "HIGH",
        }
    )

    assert isinstance(rule.applicability, RuleApplicability)
    assert rule.applicability.observation == "dom_button"
    assert len(rule.applicability.conditions.all or []) == 1
