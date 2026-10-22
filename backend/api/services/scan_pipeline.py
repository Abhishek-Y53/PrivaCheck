"""Safe, framework-configurable scan-to-report pipeline.

This module is additive: existing API services can delegate to it without
replacing route/request/response contracts in one step.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from backend.domain.rules.models import Rule
from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.loader import RuleLoader
from backend.reporting.report_builder import build_scan_report
from backend.schemas.core import CheckResult, ComplianceStatus, CrawlerResult, Observation, ScanReport
from backend.schemas.scan_request import ScanRequest
from backend.security.url_validation import URLValidationError, validate_public_http_url

logger = logging.getLogger(__name__)
DEFAULT_SCAN_TIMEOUT_SECONDS = 180.0
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Only explicitly registered framework IDs can select rule files. Never accept
# a filesystem path from request data; that would create a path traversal risk.
DEFAULT_FRAMEWORK_RULE_FILES: dict[str, Path] = {
    "gdpr": _PROJECT_ROOT / "rules" / "gdpr" / "rules.yaml",
}


class ScanPipelineError(RuntimeError):
    """Base error for controlled scan-pipeline failures."""


class UnsafeScanTargetError(ScanPipelineError):
    """The target URL did not pass the public-destination policy."""


class UnsupportedFrameworkError(ScanPipelineError):
    """The requested framework does not have a registered rule file."""


class ScanTimeoutError(ScanPipelineError):
    """The scan exceeded its configured wall-clock time limit."""


class ScanPipelineService:
    """Run URL validation -> crawler -> YAML rules -> report aggregation."""

    def __init__(
        self,
        *,
        crawler_factory: Callable[..., object] | None = None,
        rule_loader: RuleLoader | None = None,
        rule_engine: RuleEngine | None = None,
        url_validator: Callable[[str], Awaitable[str]] | None = None,
        framework_rule_files: dict[str, Path] | None = None,
        two_pass_scan: Callable[[str], Awaitable[object]] | None = None,
        scan_timeout_seconds: float = DEFAULT_SCAN_TIMEOUT_SECONDS,
    ) -> None:
        self.crawler_factory = crawler_factory
        self.rule_loader = rule_loader or RuleLoader()
        self.rule_engine = rule_engine or RuleEngine()
        self.url_validator = url_validator or validate_public_http_url
        self.two_pass_scan = two_pass_scan
        if scan_timeout_seconds <= 0:
            raise ValueError("scan_timeout_seconds must be positive")
        self.scan_timeout_seconds = scan_timeout_seconds
        self.framework_rule_files = dict(
            DEFAULT_FRAMEWORK_RULE_FILES
            if framework_rule_files is None
            else framework_rule_files
        )

    def _get_rule_file(self, framework: str) -> tuple[str, Path]:
        if not isinstance(framework, str):
            raise UnsupportedFrameworkError("Unsupported compliance framework.")
        normalized = framework.strip().lower()
        if not normalized or normalized not in self.framework_rule_files:
            raise UnsupportedFrameworkError("Unsupported compliance framework.")
        return normalized, self.framework_rule_files[normalized]

    async def scan(self, url: str, framework: str = "gdpr") -> ScanReport:
        """Run a bounded scan, cancelling crawling if the deadline is exceeded."""
        try:
            return await asyncio.wait_for(
                self._scan(url, framework),
                timeout=self.scan_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ScanTimeoutError(
                "Scan exceeded the configured time limit."
            ) from exc

    async def _scan(self, url: str, framework: str) -> ScanReport:
        """Execute a scan and return a sanitized report.

        The URL is validated syntactically by ScanRequest and asynchronously
        resolved here before the browser starts. The crawler repeats validation
        immediately before browser navigation as defense in depth.
        """
        try:
            request = ScanRequest(url=url)
        except Exception as exc:
            raise UnsafeScanTargetError("Target URL is invalid or unsupported.") from exc

        framework_id, rule_path = self._get_rule_file(framework)

        # Load local, allowlisted rules before consuming browser resources.
        rules = self.rule_loader.load(rule_path)
        if not rules:
            raise ScanPipelineError("The selected framework contains no rules.")

        try:
            validated_url = await self.url_validator(str(request.url))
        except URLValidationError as exc:
            raise UnsafeScanTargetError(
                "Target URL did not pass public-destination validation."
            ) from exc
        except Exception as exc:
            # Do not expose resolver exception strings, IPs or internal details.
            raise UnsafeScanTargetError(
                "Target URL could not be validated safely."
            ) from exc

        crawler_factory = self.crawler_factory
        if crawler_factory is None:
            # Lazy import keeps report/rule unit tests independent of optional
            # browser-only dependencies and avoids circular imports.
            from backend.crawler.orchestrator import CrawlerOrchestrator

            crawler_factory = CrawlerOrchestrator

        # Use the string returned by the policy validator as the canonical
        # target; the crawler repeats validation and installs request guards.
        crawler = crawler_factory(str(validated_url), headless=True)
        crawler_result: CrawlerResult = await crawler.run()

        check_results: list[CheckResult] = []
        observations: list[Observation] = crawler_result.observations

        # A failed crawl is incomplete evidence. Do not evaluate ordinary rules
        # against an empty/partial observation set, which could create false
        # FAIL/PASS conclusions. Return explicit manual-review outcomes instead.
        if getattr(crawler_result.status, "value", crawler_result.status) != "COMPLETED":
            for rule in rules:
                check_results.append(
                    self._manual_review_result(
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
                framework=framework_id,
            )

        # Run an isolated Accept/Reject scan only if at least one YAML rule
        # needs state-diff input. This avoids doubling browser work for a purely
        # declarative framework scan.
        state_diff_rules = [
            rule for rule in rules
            if str(rule.evaluator).lower() == "state_diff"
        ]
        two_pass_result = None
        two_pass_failed = False
        if state_diff_rules:
            try:
                two_pass_result = await self._run_two_pass(request.url)
            except Exception:
                two_pass_failed = True
                logger.exception(
                    "Two-pass scan failed for framework=%s", framework_id
                )

        for rule in rules:
            evaluator_name = str(rule.evaluator).lower()

            if evaluator_name == "state_diff":
                if not self._both_consent_actions_succeeded(two_pass_result):
                    check_results.append(
                        self._manual_review_result(
                            rule,
                            self._two_pass_observations(two_pass_result),
                            explanation=(
                                "The Accept/Reject comparison could not be verified "
                                "because both consent actions were not successfully "
                                "completed. No compliance conclusion was inferred."
                            ),
                        )
                    )
                    continue
                try:
                    check_results.append(
                        self.rule_engine.evaluate_rule(rule, two_pass_result)
                    )
                except Exception:
                    logger.exception(
                        "State-diff evaluation failed for check_id=%s framework=%s",
                        rule.id,
                        framework_id,
                    )
                    check_results.append(
                        self._manual_review_result(
                            rule,
                            self._two_pass_observations(two_pass_result),
                            explanation=(
                                "State-diff evaluation did not complete; manual review is required."
                            ),
                        )
                    )
                continue

            if evaluator_name != "declarative":
                # Visual/NLP evaluators remain intentionally unimplemented in
                # this pipeline. They must not silently turn into a PASS.
                check_results.append(
                    self._manual_review_result(
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
                check_results.append(
                    self.rule_engine.evaluate_rule(rule, observations)
                )
            except Exception:
                # Keep one failed rule evaluation from discarding the remaining
                # findings or causing the scan to appear compliant.
                logger.exception(
                    "Rule evaluation failed for check_id=%s framework=%s",
                    rule.id,
                    framework_id,
                )
                check_results.append(
                    self._manual_review_result(
                        rule,
                        observations,
                        explanation=(
                            "Rule evaluation did not complete; manual review is required."
                        ),
                    )
                )

        report = build_scan_report(
            crawler_result,
            check_results,
            framework=framework_id,
        )
        if state_diff_rules:
            report.metadata["two_pass"] = self._two_pass_summary(
                two_pass_result,
                failed=two_pass_failed,
            )
            accept_observations = getattr(two_pass_result, "accept_observations", []) or []
            reject_observations = getattr(two_pass_result, "reject_observations", []) or []
            two_pass_observations = list(accept_observations) + list(reject_observations)
            report.metadata["two_pass_observation_count"] = len(two_pass_observations)
            report.metadata["observation_count"] = (
                len(crawler_result.observations) + len(two_pass_observations)
            )
            combined_counts = dict(report.metadata.get("observations_by_category", {}))
            for observation in two_pass_observations:
                category = observation.category
                combined_counts[category] = combined_counts.get(category, 0) + 1
            report.metadata["observations_by_category"] = dict(sorted(combined_counts.items()))
        return report

    async def _run_two_pass(self, url: str) -> object:
        """Run the security-hardened two-pass collector with full cleanup."""
        if self.two_pass_scan is not None:
            return await self.two_pass_scan(url)

        from backend.crawler.browser import BrowserManager
        from backend.crawler.two_pass import TwoPassRunner

        manager = BrowserManager(headless=True)
        context = None
        page = None
        try:
            await manager.start()
            context, page = await manager.create_context_and_page()
            return await TwoPassRunner(
                page,
                context,
                url,
                wait_ms=3000,
                consent_wait_ms=1500,
            ).run()
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            await manager.stop()

    @staticmethod
    def _both_consent_actions_succeeded(two_pass_result: object | None) -> bool:
        if two_pass_result is None:
            return False
        if getattr(getattr(two_pass_result, "status", None), "value", getattr(two_pass_result, "status", None)) != "COMPLETED":
            return False
        for action in ("accept", "reject"):
            snapshot = getattr(two_pass_result, action, None)
            interaction = getattr(snapshot, "interaction", None)
            if getattr(interaction, "status", None) != "SUCCESS":
                return False
        return True

    @staticmethod
    def _two_pass_observations(two_pass_result: object | None) -> list[Observation]:
        if two_pass_result is None:
            return []
        combined: list[Observation] = []
        for attribute in ("accept_observations", "reject_observations"):
            observations = getattr(two_pass_result, attribute, []) or []
            combined.extend(observations)
        return combined[:40]

    @staticmethod
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

    @staticmethod
    def _manual_review_result(
        rule: Rule,
        observations: list[Observation],
        *,
        explanation: str,
    ) -> CheckResult:
        """Create a safe explicit result when a rule cannot be evaluated."""
        from backend.schemas.core import SeverityLevel

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
            severity=rule.severity if hasattr(rule, "severity") else SeverityLevel.MEDIUM,
            confidence=0.0,
            explanation=explanation,
            recommendation=getattr(rule, "recommendation", None),
            evidence=evidence,
        )
