from backend.domain.rules.models import (
    Rule,
    RuleCondition,
    RuleConditions,
    RuleResult,
    RuleSource,
)
from backend.rule_engine.engine import RuleEngine
from backend.schemas.core import Observation


def make_rule() -> Rule:
    return Rule(
        id="GDPR-024",
        name="HTTPS transport",
        description="Checks whether the main navigation request uses HTTPS.",
        category="SECURITY",
        source=RuleSource(
            observation="network_request",
            match="any",
        ),
        evaluator="declarative",
        conditions=RuleConditions(
            all=[
                RuleCondition(
                    field="is_navigation_request",
                    operator="equals",
                    value=True,
                ),
                RuleCondition(
                    field="protocol",
                    operator="equals",
                    value="https",
                ),
            ]
        ),
        result=RuleResult(
            **{
                "pass": "PASS",
                "fail": "FAIL",
            }
        ),
        severity="HIGH",
        recommendation=(
            "Serve the website and its main navigation over HTTPS "
            "and ensure that TLS certificates are correctly configured."
        ),
    )


def observation(
    protocol: str,
    is_navigation_request: bool,
) -> Observation:
    return Observation(
        category="network_request",
        source_url="https://example.com",
        timestamp=1.0,
        data={
            "url": "https://example.com",
            "protocol": protocol,
            "method": "GET",
            "resource_type": "document",
            "is_navigation_request": is_navigation_request,
        },
    )


def test_https_navigation_passes():
    rule = make_rule()

    observations = [
        observation(
            protocol="https",
            is_navigation_request=True,
        ),
        observation(
            protocol="http",
            is_navigation_request=False,
        ),
    ]

    result = RuleEngine().evaluate_rule(
        rule,
        observations,
    )

    assert result.status.value == "PASS"
    assert len(result.evidence) == 1
    assert result.evidence[0].data["protocol"] == "https"


def test_http_navigation_fails_even_when_other_https_requests_exist():
    rule = make_rule()

    observations = [
        observation(
            protocol="http",
            is_navigation_request=True,
        ),
        observation(
            protocol="https",
            is_navigation_request=False,
        ),
    ]

    result = RuleEngine().evaluate_rule(
        rule,
        observations,
    )

    assert result.status.value == "FAIL"
    assert result.evidence == []


from backend.domain.rules.models import (
    Rule,
    RuleConditions,
    RuleResult,
    RuleSource,
)
from backend.rule_engine.engine import RuleEngine
from backend.schemas.core import (
    ComplianceStatus,
    Observation,
    SeverityLevel,
)


def make_gdpr_024_rule() -> Rule:
    return Rule(
        id="GDPR-024",
        name="HTTPS with valid TLS certificate",
        description=(
            "Checks whether the final page URL is served over HTTPS "
            "with a valid TLS certificate."
        ),
        category="SECURITY",
        source=RuleSource(
            observation="tls_certificate",
            match="all",
        ),
        evaluator="declarative",
        conditions=RuleConditions(
            all=[
                {
                    "field": "protocol",
                    "operator": "equals",
                    "value": "https",
                },
                {
                    "field": "verified",
                    "operator": "equals",
                    "value": True,
                },
            ]
        ),
        result=RuleResult(
            **{
                "pass": ComplianceStatus.PASS,
                "fail": ComplianceStatus.FAIL,
            }
        ),
        severity=SeverityLevel.HIGH,
        recommendation=(
            "Serve the website over HTTPS with a valid TLS certificate."
        ),
    )


def make_tls_observation(
    protocol: str,
    verified: bool,
) -> Observation:
    return Observation(
        category="tls_certificate",
        source_url="https://example.com/",
        timestamp=1.0,
        data={
            "url": "https://example.com/",
            "hostname": "example.com",
            "port": 443,
            "protocol": protocol,
            "verified": verified,
        },
    )


def test_gdpr_024_passes_with_valid_https_certificate():
    rule = make_gdpr_024_rule()

    result = RuleEngine().evaluate_rule(
        rule,
        [
            make_tls_observation(
                protocol="https",
                verified=True,
            )
        ],
    )

    assert result.status == ComplianceStatus.PASS


def test_gdpr_024_fails_with_invalid_certificate():
    rule = make_gdpr_024_rule()

    result = RuleEngine().evaluate_rule(
        rule,
        [
            make_tls_observation(
                protocol="https",
                verified=False,
            )
        ],
    )

    assert result.status == ComplianceStatus.FAIL


def test_gdpr_024_fails_for_http():
    rule = make_gdpr_024_rule()

    result = RuleEngine().evaluate_rule(
        rule,
        [
            make_tls_observation(
                protocol="http",
                verified=False,
            )
        ],
    )

    assert result.status == ComplianceStatus.FAIL


def test_gdpr_024_fails_without_tls_observation():
    rule = make_gdpr_024_rule()

    result = RuleEngine().evaluate_rule(
        rule,
        [],
    )

    assert result.status == ComplianceStatus.FAIL


def test_gdpr_024_ignores_unrelated_observations():
    rule = make_gdpr_024_rule()

    tls_observation = make_tls_observation(
        protocol="https",
        verified=True,
    )

    unrelated_observation = Observation(
        category="dom_button",
        source_url="https://example.com/",
        timestamp=1.0,
        data={
            "text": "Accept Cookies",
        },
    )

    result = RuleEngine().evaluate_rule(
        rule,
        [
            unrelated_observation,
            tls_observation,
        ],
    )

    assert result.status == ComplianceStatus.PASS


def test_gdpr_024_fails_when_one_tls_observation_is_invalid():
    rule = make_gdpr_024_rule()

    valid_tls = make_tls_observation(
        protocol="https",
        verified=True,
    )

    invalid_tls = make_tls_observation(
        protocol="https",
        verified=False,
    )

    result = RuleEngine().evaluate_rule(
        rule,
        [
            valid_tls,
            invalid_tls,
        ],
    )

    assert result.status == ComplianceStatus.FAIL