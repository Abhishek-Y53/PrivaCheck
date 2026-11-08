"""Safe, framework-configurable synchronous scan-to-report pipeline.

The crawler remains in this API pipeline for compatibility. Rule evaluation
itself is delegated to the shared evaluator also used by the Celery worker.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from backend.reporting.report_builder import build_scan_report
from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.framework_registry import (
    DEFAULT_FRAMEWORK_RULE_FILES,
    FrameworkRegistry,
    UnsupportedFrameworkError as RegistryFrameworkError,
)
from backend.rule_engine.loader import RuleLoader
from backend.rule_engine.scan_evaluator import evaluate_observations
from backend.schemas.core import CrawlerResult, Observation, ScanReport
from backend.schemas.scan_request import ScanRequest
from backend.security.url_validation import URLValidationError, validate_public_http_url

logger = logging.getLogger(__name__)
ObservationSink = Callable[[list[Observation]], Awaitable[None]]
DEFAULT_SCAN_TIMEOUT_SECONDS = 180.0


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
        self.framework_registry = FrameworkRegistry(self.framework_rule_files)

    def _get_rule_file(self, framework: str) -> tuple[str, Path]:
        try:
            return self.framework_registry.resolve(framework)
        except RegistryFrameworkError as exc:
            raise UnsupportedFrameworkError("Unsupported compliance framework.") from exc

    async def scan(
        self,
        url: str,
        framework: str = "gdpr",
        *,
        observation_sink: ObservationSink | None = None,
    ) -> ScanReport:
        """Run a bounded scan, optionally staging observations before evaluation."""
        try:
            if observation_sink is None:
                scan_coroutine = self._scan(url, framework)
            else:
                scan_coroutine = self._scan(
                    url,
                    framework,
                    observation_sink=observation_sink,
                )
            return await asyncio.wait_for(
                scan_coroutine,
                timeout=self.scan_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ScanTimeoutError(
                "Scan exceeded the configured time limit."
            ) from exc

    async def _scan(
        self,
        url: str,
        framework: str,
        *,
        observation_sink: ObservationSink | None = None,
    ) -> ScanReport:
        """Execute a scan and return a sanitized report."""
        try:
            request = ScanRequest(url=url)
        except Exception as exc:
            raise UnsafeScanTargetError("Target URL is invalid or unsupported.") from exc

        framework_id, rule_path = self._get_rule_file(framework)
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
            raise UnsafeScanTargetError(
                "Target URL could not be validated safely."
            ) from exc

        crawler_factory = self.crawler_factory
        if crawler_factory is None:
            from backend.crawler.orchestrator import CrawlerOrchestrator

            crawler_factory = CrawlerOrchestrator

        crawler = crawler_factory(str(validated_url), headless=True)
        crawler_result: CrawlerResult = await crawler.run()
        observations = list(crawler_result.observations)

        if str(getattr(crawler_result.status, "value", crawler_result.status)).upper() != "COMPLETED":
            await self._emit_observations(observation_sink, observations)
            return evaluate_observations(
                crawler_result,
                rules,
                framework=framework_id,
                rule_engine=self.rule_engine,
            )

        state_diff_rules = [
            rule for rule in rules
            if str(rule.evaluator).strip().lower() == "state_diff"
        ]
        two_pass_result = None
        two_pass_failed = False
        if state_diff_rules:
            try:
                two_pass_result = await self._run_two_pass(str(request.url))
            except Exception:
                two_pass_failed = True
                logger.exception(
                    "Two-pass scan failed for framework=%s", framework_id
                )

        staged_observations = observations + self._all_two_pass_observations(two_pass_result)
        await self._emit_observations(observation_sink, staged_observations)

        return evaluate_observations(
            crawler_result,
            rules,
            framework=framework_id,
            rule_engine=self.rule_engine,
            two_pass_result=two_pass_result,
            two_pass_failed=two_pass_failed,
        )

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
                    logger.exception("Failed to close the two-pass page")
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    logger.exception("Failed to close the two-pass context")
            await manager.stop()

    @staticmethod
    async def _emit_observations(
        observation_sink: ObservationSink | None,
        observations: list[Observation],
    ) -> None:
        """Await the optional persistence handoff before rule evaluation."""
        if observation_sink is not None:
            await observation_sink(observations)

    @staticmethod
    def _all_two_pass_observations(two_pass_result: object | None) -> list[Observation]:
        if two_pass_result is None:
            return []
        combined: list[Observation] = []
        for attribute in ("accept_observations", "reject_observations"):
            combined.extend(getattr(two_pass_result, attribute, None) or [])
        return combined
