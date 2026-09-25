from backend.schemas.core import ComplianceStatus
from pathlib import Path

from backend.crawler.browser import BrowserManager
from backend.crawler.orchestrator import CrawlerOrchestrator
from backend.crawler.two_pass import TwoPassResult, TwoPassRunner
from backend.domain.rules.models import Rule
from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.loader import RuleLoader

from backend.api.schemas import (
    ScanRequest,
    ScanResponse,
)


class ScanService:
    """
    Application service responsible for executing a compliance scan.

    The service coordinates existing components but does not implement
    crawler logic or compliance rules itself.
    """

    def __init__(self) -> None:
        self.rule_loader = RuleLoader()
        self.rule_engine = RuleEngine()

    def _get_rules_path(
        self,
        framework: str,
    ) -> Path:
        """
        Resolve the rule file for the selected framework.
        """

        project_root = (
            Path(__file__)
            .resolve()
            .parents[3]
        )

        rule_path = (
            project_root
            / "rules"
            / framework
            / "rules.yaml"
        )

        if not rule_path.exists():
            raise FileNotFoundError(
                f"Rule file not found: {rule_path}"
            )

        return rule_path

    def _load_rules(
        self,
        framework: str,
    ) -> list[Rule]:
        """
        Load and validate the selected rule set.
        """

        rule_path = self._get_rules_path(
            framework
        )

        return self.rule_loader.load(
            rule_path
        )

    async def _run_normal_scan(
        self,
        website: str,
    ):
        """
        Run the standard one-pass crawler.
        """

        crawler = CrawlerOrchestrator(
            url=website,
            headless=True,
        )

        return await crawler.run()

    async def _run_two_pass_scan(
        self,
        website: str,
    ) -> TwoPassResult:
        """
        Run the isolated Accept/Reject scan.
        """

        browser_manager = BrowserManager(
            headless=True
        )

        await browser_manager.start()

        context = None
        page = None

        try:
            context, page = (
                await browser_manager
                .create_context_and_page()
            )

            runner = TwoPassRunner(
                page=page,
                context=context,
                url=website,
            )

            return await runner.run()

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

            await browser_manager.stop()

    @staticmethod
    def _overall_status(results):
        """
        Determine the overall scan status.

        NOT_APPLICABLE is neutral:
        - FAIL has highest priority.
        - MANUAL_REVIEW follows.
        - WARNING follows.
        - If every rule is NOT_APPLICABLE, return NOT_APPLICABLE.
        - Otherwise, a scan with no blocking issues is PASS.
        """

        if not results:
            return ComplianceStatus.PASS

        statuses = {result.status for result in results}

        if ComplianceStatus.FAIL in statuses:
            return ComplianceStatus.FAIL

        if ComplianceStatus.MANUAL_REVIEW in statuses:
            return ComplianceStatus.MANUAL_REVIEW

        if ComplianceStatus.WARNING in statuses:
            return ComplianceStatus.WARNING

        if statuses == {ComplianceStatus.NOT_APPLICABLE}:
            return ComplianceStatus.NOT_APPLICABLE

        return ComplianceStatus.PASS



  

    async def scan(
        self,
        request: ScanRequest,
    ) -> ScanResponse:
        """
        Execute a compliance scan for the requested framework.
        """

        website = str(request.website)

        rules = self._load_rules(
            request.framework
        )

        if not rules:
            raise ValueError(
                "The selected framework contains no rules."
            )

        declarative_rules = [
            rule
            for rule in rules
            if rule.evaluator == "declarative"
        ]

        state_diff_rules = [
            rule
            for rule in rules
            if rule.evaluator == "state_diff"
        ]

        results = []

        observation_count = 0

        # ---------------------------------------------------------
        # Declarative rules
        # ---------------------------------------------------------

        if declarative_rules:

            crawler_result = (
                await self._run_normal_scan(
                    website
                )
            )

            if crawler_result.status.value != "COMPLETED":
                raise RuntimeError(
                    crawler_result.error
                    or "Crawler failed."
                )

            observation_count += len(
                crawler_result.observations
            )

            declarative_results = (
                self.rule_engine.evaluate_rules(
                    declarative_rules,
                    crawler_result.observations,
                )
            )

            results.extend(
                declarative_results
            )

        # ---------------------------------------------------------
        # State-diff rules
        # ---------------------------------------------------------

        if state_diff_rules:

            two_pass_result = (
                await self._run_two_pass_scan(
                    website
                )
            )

            if (
                two_pass_result.status.value
                != "COMPLETED"
            ):
                raise RuntimeError(
                    two_pass_result.error
                    or "Two-pass crawler failed."
                )

            observation_count += (
                len(
                    two_pass_result.accept_observations
                )
                + len(
                    two_pass_result.reject_observations
                )
            )

            state_diff_results = (
                self.rule_engine.evaluate_rules(
                    state_diff_rules,
                    two_pass_result,
                )
            )

            results.extend(
                state_diff_results
            )

        passed_checks = sum(
            result.status.value == "PASS"
            for result in results
        )

        failed_checks = sum(
            result.status.value == "FAIL"
            for result in results
        )

        return ScanResponse(
            website=website,
            framework=request.framework,
            status=self._overall_status(
                results
            ),
            total_checks=len(results),
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            observation_count=observation_count,
            results=results,
            error=None,
        )