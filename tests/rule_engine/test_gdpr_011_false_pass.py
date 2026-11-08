from pathlib import Path

from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.loader import RuleLoader
from backend.schemas.core import Observation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = PROJECT_ROOT / "rules" / "gdpr" / "rules.yaml"


def make_link(*, text: str, href: str, context_text: str = "") -> Observation:
    return Observation(
        category="link",
        source_url="https://example.test/",
        timestamp=1.0,
        data={
            "text": text,
            "href": href,
            "context_text": context_text,
        },
    )


def evaluate_gdpr_011(observations: list[Observation]):
    rules = RuleLoader().load(RULES_PATH)
    rule = next(rule for rule in rules if rule.id == "GDPR-011")
    return RuleEngine().evaluate_rule(rule, observations)


def status_value(result) -> str:
    return str(getattr(result.status, "value", result.status))


def test_ccpa_style_do_not_sell_link_does_not_pass_gdpr_objection_check():
    result = evaluate_gdpr_011(
        [
            make_link(
                text="Do not share or sell my info",
                href="https://example.test/privacy-choices",
                context_text="Your privacy choices",
            )
        ]
    )
    assert status_value(result) == "FAIL"


def test_generic_opt_out_link_does_not_pass_gdpr_objection_check():
    result = evaluate_gdpr_011(
        [
            make_link(
                text="Opt out",
                href="https://example.test/opt-out",
                context_text="Manage your privacy preferences",
            )
        ]
    )
    assert status_value(result) == "FAIL"


def test_explicit_objection_to_processing_link_passes():
    result = evaluate_gdpr_011(
        [
            make_link(
                text="Object to processing",
                href="https://example.test/object-to-processing",
                context_text="Learn how to object to the processing of your data",
            )
        ]
    )
    assert status_value(result) == "PASS"
