"""Two-pass browser-state collection for consent-dependent analysis."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Sequence

from playwright.async_api import Browser, BrowserContext, Page

from backend.crawler.pass_runner import SinglePassRunner
from backend.schemas.core import CrawlerStatus, Observation
from backend.security.url_validation import normalize_http_url


ConsentAction = Literal["accept", "reject"]

ConsentInteractionStatus = Literal[
    "SUCCESS",
    "NOT_FOUND",
    "FAILED",
]


@dataclass(frozen=True)
class ConsentInteractionResult:
    """
    Raw result of attempting a consent action.

    This does not determine compliance.
    """

    action: ConsentAction
    status: ConsentInteractionStatus
    matched_text: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.status == "SUCCESS"


@dataclass(frozen=True)
class PassSnapshot:
    """Observations collected for one isolated browser state."""

    action: ConsentAction
    target_url: str
    final_url: str
    observations: list[Observation]
    started_at: float
    completed_at: float
    status: CrawlerStatus
    interaction: ConsentInteractionResult
    error: str | None = None


@dataclass(frozen=True)
class TwoPassResult:
    """Complete result of the isolated Accept/Reject scan."""

    target_url: str
    accept: PassSnapshot | None
    reject: PassSnapshot | None
    started_at: float
    completed_at: float
    status: CrawlerStatus
    error: str | None = None

    @property
    def accept_observations(self) -> list[Observation]:
        return (
            self.accept.observations
            if self.accept
            else []
        )

    @property
    def reject_observations(self) -> list[Observation]:
        return (
            self.reject.observations
            if self.reject
            else []
        )


@dataclass(frozen=True)
class ConsentActionConfig:
    """
    Labels used to locate likely Accept-All and Reject-All controls.
    """

    accept_labels: Sequence[str] = (
        "accept all",
        "accept all cookies",
        "allow all",
        "allow all cookies",
        "agree to all",
        "agree to all cookies",
        "consent to all",
        "i agree to all",
        "accept",
        "agree",
    )

    reject_labels: Sequence[str] = (
        "reject all",
        "reject all cookies",
        "decline all",
        "decline all cookies",
        "deny all",
        "deny all cookies",
        "refuse all",
        "refuse all cookies",
        "only necessary",
        "necessary only",
        "use necessary cookies only",
        "reject",
        "decline",
        "deny",
    )

    selectors: Sequence[str] = (
        "button",
        "[role='button']",
        "input[type='button']",
        "input[type='submit']",
    )


class TwoPassRunner:
    """
    Run two isolated browser passes:

        Pass 1 -> Accept
        Pass 2 -> Reject

    The runner only collects browser-state evidence.
    It does not determine compliance.
    """

    def __init__(
        self,
        page: Page,
        context: BrowserContext,
        url: str,
        *,
        wait_ms: int = 3000,
        consent_wait_ms: int = 1500,
        consent_config: ConsentActionConfig | None = None,
    ) -> None:

        self.page = page
        self.context = context
        self.url = normalize_http_url(url)
        self.wait_ms = wait_ms
        self.consent_wait_ms = consent_wait_ms
        self.consent_config = (
            consent_config
            or ConsentActionConfig()
        )

        browser = context.browser

        if browser is None:
            raise RuntimeError(
                "TwoPassRunner requires a "
                "BrowserContext backed by a browser."
            )

        self.browser: Browser = browser

    async def run(self) -> TwoPassResult:
        started_at = time.time()

        accept_snapshot = await self._run_pass(
            "accept"
        )

        reject_snapshot = await self._run_pass(
            "reject"
        )

        errors: list[str] = []

        if accept_snapshot.status == CrawlerStatus.FAILED:
            errors.append(
                f"accept pass failed: "
                f"{accept_snapshot.error}"
            )

        if reject_snapshot.status == CrawlerStatus.FAILED:
            errors.append(
                f"reject pass failed: "
                f"{reject_snapshot.error}"
            )

        return TwoPassResult(
            target_url=self.url,
            accept=accept_snapshot,
            reject=reject_snapshot,
            started_at=started_at,
            completed_at=time.time(),
            status=(
                CrawlerStatus.FAILED
                if errors
                else CrawlerStatus.COMPLETED
            ),
            error=(
                "; ".join(errors)
                if errors
                else None
            ),
        )

    async def _run_pass(
        self,
        action: ConsentAction,
    ) -> PassSnapshot:

        pass_context: BrowserContext | None = None
        pass_page: Page | None = None

        try:
            # IMPORTANT:
            # Create a completely new context for every pass.
            pass_context = (
                await self.browser.new_context(service_workers="block")
            )

            pass_page = (
                await pass_context.new_page()
            )

            async def consent_action(
                page: Page,
            ) -> ConsentInteractionResult:

                return (
                    await self._interact_with_consent(
                        page,
                        action,
                    )
                )

            # Reuse the shared crawler workflow.
            runner = SinglePassRunner(
                pass_page,
                pass_context,
                self.url,
                wait_ms=self.wait_ms,
                post_action_wait_ms=self.consent_wait_ms,
            )

            result = await runner.run(
                post_navigation_action=consent_action
            )

            interaction = result.action_result

            if not isinstance(
                interaction,
                ConsentInteractionResult,
            ):
                interaction = ConsentInteractionResult(
                    action=action,
                    status="FAILED",
                    error=(
                        "Consent interaction did not "
                        "return a valid result."
                    ),
                )

            return PassSnapshot(
                action=action,
                target_url=self.url,
                final_url=result.final_url,
                observations=result.observations,
                started_at=result.started_at,
                completed_at=result.completed_at,
                status=result.status,
                interaction=interaction,
                error=result.error,
            )

        finally:
            if pass_page is not None:
                try:
                    await pass_page.close()
                except Exception:
                    pass

            if pass_context is not None:
                try:
                    await pass_context.close()
                except Exception:
                    pass

    async def _interact_with_consent(
        self,
        page: Page,
        action: ConsentAction,
    ) -> ConsentInteractionResult:

        labels = (
            self.consent_config.accept_labels
            if action == "accept"
            else self.consent_config.reject_labels
        )

        normalized_labels = [
            self._normalize_text(label)
            for label in labels
        ]

        candidates: list[
            tuple[int, str, object]
        ] = []

        try:
            for frame in page.frames:

                for selector in (
                    self.consent_config.selectors
                ):

                    locator = frame.locator(
                        selector
                    )

                    try:
                        count = await locator.count()
                    except Exception:
                        continue

                    for index in range(count):

                        element = locator.nth(
                            index
                        )

                        try:
                            if not await element.is_visible():
                                continue

                            text = (
                                await self._candidate_text(
                                    element
                                )
                            )

                        except Exception:
                            continue

                        normalized = (
                            self._normalize_text(text)
                        )

                        if not normalized:
                            continue

                        score = (
                            self._score_candidate(
                                normalized,
                                normalized_labels,
                                action,
                            )
                        )

                        if score > 0:
                            candidates.append(
                                (
                                    score,
                                    text,
                                    element,
                                )
                            )

            # No Accept/Reject control.
            if not candidates:

                return ConsentInteractionResult(
                    action=action,
                    status="NOT_FOUND",
                    error=(
                        f"No suitable {action} "
                        "consent control was found "
                        "on the page."
                    ),
                )

            # Highest score first.
            candidates.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            _, matched_text, element = (
                candidates[0]
            )

            try:
                await element.click(
                    timeout=3000
                )

            except Exception as exc:

                return ConsentInteractionResult(
                    action=action,
                    status="FAILED",
                    matched_text=matched_text,
                    error=(
                        f"Failed to click "
                        f"'{matched_text}': {exc}"
                    ),
                )

            return ConsentInteractionResult(
                action=action,
                status="SUCCESS",
                matched_text=matched_text,
            )

        except Exception as exc:

            return ConsentInteractionResult(
                action=action,
                status="FAILED",
                error=(
                    f"Consent detection failed: "
                    f"{exc}"
                ),
            )

    @staticmethod
    async def _candidate_text(
        element: object,
    ) -> str:

        parts: list[str] = []

        for attr in (
            "aria-label",
            "value",
            "title",
        ):

            try:
                value = await element.get_attribute(
                    attr
                )  # type: ignore[attr-defined]

            except Exception:
                value = None

            if value:
                parts.append(value)

        try:
            inner_text = await element.inner_text()
        except Exception:
            inner_text = ""

        if inner_text:
            parts.append(inner_text)

        return " ".join(parts)

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:

        return " ".join(
            text.lower().split()
        )

    @staticmethod
    def _score_candidate(
        text: str,
        labels: Sequence[str],
        action: ConsentAction,
    ) -> int:

        score = 0

        excluded_terms = (
            "settings",
            "preferences",
            "customize",
            "customise",
            "manage cookies",
            "learn more",
        )

        if any(
            term in text
            for term in excluded_terms
        ):
            return 0

        for label in labels:

            if text == label:
                score = max(
                    score,
                    100,
                )

            elif (
                text.startswith(label + " ")
                or text.endswith(" " + label)
            ):
                score = max(
                    score,
                    80,
                )

            elif f" {label} " in (
                f" {text} "
            ):
                score = max(
                    score,
                    60,
                )

        if "all" in text:
            score += 20

        # Be slightly more conservative with
        # generic "Accept"/"Agree".
        if (
            action == "accept"
            and text in {"accept", "agree"}
        ):
            score -= 10

        return max(score, 0)