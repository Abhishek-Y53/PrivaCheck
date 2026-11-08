"""Reusable rule-evaluation/reporting logic shared by sync and async scans."""

from __future__ import annotations

import logging
from typing import Iterable

from backend.domain.rules.models import Rule
from backend.reporting.report_builder import build_scan_report
from backend.rule_engine.engine import RuleEngine
from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
    CrawlerResult,
    SeverityLevel,
    ScanReport,
)

logger = logging.getLogger(__name__)


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value)).upper()


def _all_two_pass_observations(two_pass_result: object | None) -> list:
    if two_pass_result is None:
        return []
    combined = []
    for attribute in ("accept_observations", "reject_observations"):
        combined.extend(getattr(two_pass_result, attribute, None) or [])
    return combined


def _two_pass_observations(two_pass_result: object | None) -> list:
    # Match the existing bounded evidence behaviour for manual-review findings.
    return _all_two_pass_observations(two_pass_result)[:40]


def _both_consent_actions_succeeded(two_pass_result: object | None) -> bool:
    if two_pass_result is None:
        return False
    if _status_value(getattr(two_pass_result, "status", None)) != "COMPLETED":
        return False
    for action in ("accept", "reject"):
        snapshot = getattr(two_pass_result, action, None)
        interaction = getattr(snapshot, "interaction", None)
        if getattr(interaction, "status", None) != "SUCCESS":
            return False
    return True


def manual_review_result(
    rule: Rule,
    observations: list,
    *,
    explanation: str,
) -> CheckResult:
    """Create an explicit non-conclusive result with bounded relevant evidence."""
    source_category = getattr(getattr(rule, "source", None), "observation", None)
    evidence = [
        observation
        for observation in observations
        if source_category is None or observation.category == source_category
    ][:20]
    return CheckResult(
        check_id=rule.id,
        name=rule.name,
        status=ComplianceStatus.MANUAL_REVIEW,
        severity=getattr(rule, "severity", SeverityLevel.MEDIUM),
        confidence=0.0,
        explanation=explanation,
        recommendation=getattr(rule, "recommendation", None),
        evidence=evidence,
    )


def evaluate_observations(
    crawler_result: CrawlerResult,
    rules: Iterable[Rule],
    *,
    framework: str,
    rule_engine: RuleEngine | None = None,
    two_pass_result: object | None = None,
    two_pass_failed: bool = False,
    scan_id: str | None = None,
) -> ScanReport:
    """Evaluate already-collected evidence and construct the sanitized report.

    This function intentionally performs no crawling, database work, broker
    communication, or filesystem path selection. Both the synchronous API
    pipeline and asynchronous compliance worker call this same function.

    State-diff rules require a successful TwoPassResult. A normal list of
    observations is not sufficient evidence for that evaluator.
    """
    rule_list = list(rules)
    engine = rule_engine or RuleEngine()
    observations = list(crawler_result.observations)
    check_results: list[CheckResult] = []

    if _status_value(crawler_result.status) != "COMPLETED":
        for rule in rule_list:
            check_results.append(
                manual_review_result(
                    rule,
                    observations,
                    explanation=(
                        "The crawler did not complete successfully; the rule "
                        "could not be assessed reliably and requires manual review."
                    ),
                )
            )
        return build_scan_report(
            crawler_result,
            check_results,
            framework=framework,
            scan_id=scan_id,
        )

    for rule in rule_list:
        evaluator_name = str(rule.evaluator).strip().lower()

        if evaluator_name == "state_diff":
            if not _both_consent_actions_succeeded(two_pass_result):
                check_results.append(
                    manual_review_result(
                        rule,
                        _two_pass_observations(two_pass_result),
                        explanation=(
                            "The Accept/Reject comparison could not be verified "
                            "because both consent actions were not successfully "
                            "completed. No compliance conclusion was inferred."
                        ),
                    )
                )
                continue
            try:
                check_results.append(engine.evaluate_rule(rule, two_pass_result))
            except Exception:
                logger.exception(
                    "State-diff evaluation failed for check_id=%s framework=%s",
                    rule.id,
                    framework,
                )
                check_results.append(
                    manual_review_result(
                        rule,
                        _two_pass_observations(two_pass_result),
                        explanation=(
                            "State-diff evaluation did not complete; manual review is required."
                        ),
                    )
                )
            continue

        if evaluator_name != "declarative":
            check_results.append(
                manual_review_result(
                    rule,
                    observations,
                    explanation=(
                        f"Rule requires the '{evaluator_name}' evaluator, "
                        "which is not available in this pipeline."
                    ),
                )
            )
            continue

        try:
            check_results.append(engine.evaluate_rule(rule, observations))
        except Exception:
            # One broken rule must not discard independent findings or become PASS.
            logger.exception(
                "Rule evaluation failed for check_id=%s framework=%s",
                rule.id,
                framework,
            )
            check_results.append(
                manual_review_result(
                    rule,
                    observations,
                    explanation="Rule evaluation did not complete; manual review is required.",
                )
            )

    report = build_scan_report(
        crawler_result,
        check_results,
        framework=framework,
        scan_id=scan_id,
    )

    state_diff_rules = [
        rule for rule in rule_list if str(rule.evaluator).strip().lower() == "state_diff"
    ]
    if state_diff_rules:
        report.metadata["two_pass"] = _two_pass_summary(
            two_pass_result,
            failed=two_pass_failed,
        )
        two_pass_observations = _all_two_pass_observations(two_pass_result)
        report.metadata["two_pass_observation_count"] = len(two_pass_observations)
        report.metadata["observation_count"] = len(observations) + len(two_pass_observations)
        combined_counts = dict(report.metadata.get("observations_by_category", {}))
        for observation in two_pass_observations:
            category = observation.category
            combined_counts[category] = combined_counts.get(category, 0) + 1
        report.metadata["observations_by_category"] = dict(sorted(combined_counts.items()))

    return report


def _two_pass_summary(two_pass_result: object | None, *, failed: bool) -> dict[str, object]:
    if two_pass_result is None:
        return {"available": False, "scan_failed": failed}

    def snapshot_summary(action: str) -> dict[str, object]:
        snapshot = getattr(two_pass_result, action, None)
        interaction = getattr(snapshot, "interaction", None)
        status = getattr(snapshot, "status", None)
        return {
            "pass_status": getattr(status, "value", status),
            "interaction_status": getattr(interaction, "status", None),
            "matched_control": bool(getattr(interaction, "matched_text", None)),
        }

    status = getattr(two_pass_result, "status", None)
    return {
        "available": True,
        "scan_status": getattr(status, "value", status),
        "scan_failed": failed,
        "accept": snapshot_summary("accept"),
        "reject": snapshot_summary("reject"),
    }
