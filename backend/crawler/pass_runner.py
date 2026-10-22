"""Shared single-pass browser execution for PrivaCheck crawlers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from playwright.async_api import BrowserContext, Page

from backend.crawler.cookies import CookieCollector
from backend.crawler.dom import DOMCollector
from backend.crawler.links import LinkCollector
from backend.crawler.network import NetworkCollector
from backend.crawler.storage import StorageCollector
from backend.schemas.core import CrawlerStatus, Observation
from backend.security.url_validation import (
    PublicNetworkGuard,
    URLValidationError,
    validate_public_http_url,
)


PostNavigationAction = Callable[[Page], Awaitable[Any]]


@dataclass(frozen=True)
class SinglePassResult:
    """Result of one isolated page execution and observation pass."""

    target_url: str
    final_url: str
    observations: list[Observation]
    started_at: float
    completed_at: float
    status: CrawlerStatus
    action_result: Any = None
    error: str | None = None


class SinglePassRunner:
    """
    Run one browser page pass and collect all standard observations.

    This class contains the common crawling sequence used by:
    - normal one-pass crawling
    - two-pass Accept/Reject crawling

    It does not perform compliance analysis.
    """

    def __init__(
        self,
        page: Page,
        context: BrowserContext,
        url: str,
        *,
        wait_ms: int = 3000,
        post_action_wait_ms: int = 0,
    ) -> None:
        self.page = page
        self.context = context
        self.url = url
        self.wait_ms = wait_ms
        self.post_action_wait_ms = post_action_wait_ms

    @staticmethod
    def _copy_with_consent_phase(
        observations: list[Observation],
        phase: str,
    ) -> list[Observation]:
        """Copy observations and tag the browser state they describe."""
        tagged: list[Observation] = []
        for observation in observations:
            copied = observation.model_copy(deep=True)
            copied.data["consent_phase"] = phase
            tagged.append(copied)
        return tagged

    @staticmethod
    def _copy_network_with_consent_phase(
        observations: list[Observation],
        default_phase: str,
        request_phases: dict[str, str],
    ) -> list[Observation]:
        """Tag network events, correlating responses to their request phase."""
        tagged: list[Observation] = []
        for observation in observations:
            request_id = observation.data.get("request_id")
            phase = default_phase

            if observation.category == "network_request":
                if request_id:
                    request_phases[str(request_id)] = default_phase
            elif observation.category == "network_response" and request_id:
                # A response may arrive after the consent click even though
                # its request was sent before the click. Preserve request time.
                phase = request_phases.get(str(request_id), default_phase)

            copied = observation.model_copy(deep=True)
            copied.data["consent_phase"] = phase
            tagged.append(copied)
        return tagged

    async def run(
        self,
        post_navigation_action: PostNavigationAction | None = None,
    ) -> SinglePassResult:
        """
        Navigate, optionally capture a pre-action state, run the action,
        and collect the resulting state.

        In two-pass consent scans, DOM/cookie/storage snapshots and network
        events are tagged as before_consent or after_consent. A failed or
        missing consent interaction does not label observations as after consent.
        """

        started_at = time.time()
        observations: list[Observation] = []
        final_url = ""
        validated_url = ""
        action_result: Any = None
        network_collector: NetworkCollector | None = None
        network_observation_count_recorded = 0
        consent_action_succeeded: bool | None = None
        network_request_phases: dict[str, str] = {}

        try:
            # Validate the initial destination before Chromium can contact it.
            # The browser-level guard then validates redirects, subresources and
            # WebSockets as well. Service workers are disabled on the context.
            validated_url = await validate_public_http_url(self.url)
            request_guard = PublicNetworkGuard()
            await request_guard.install(self.context)

            # Start network collection before navigation, after the guard has
            # been installed, so initial page-load requests are captured safely.
            network_collector = NetworkCollector(
                self.page,
                validated_url,
            )
            network_collector.start_collecting()

            await self.page.goto(
                validated_url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self.page.wait_for_timeout(self.wait_ms)
            final_url = self.page.url

            if post_navigation_action is not None:
                # Capture the actual browser state before the consent action.
                before_state = await self.collect_current_state(
                    self.page,
                    self.context,
                    final_url,
                )
                observations.extend(
                    self._copy_with_consent_phase(
                        before_state,
                        "before_consent",
                    )
                )

                # Snapshot all network observations collected up to this point.
                # Copying prevents later phase tags from mutating earlier evidence.
                network_before_action = network_collector.get_observations()
                pre_action_count = len(network_before_action)
                observations.extend(
                    self._copy_network_with_consent_phase(
                        network_before_action,
                        "before_consent",
                        network_request_phases,
                    )
                )
                network_observation_count_recorded = pre_action_count

                # Perform Accept or Reject only after the pre-consent snapshot.
                action_result = await post_navigation_action(self.page)

                # Structured consent results explicitly report success/failure.
                # For generic callbacks, a normal return means the action ran
                # successfully unless it explicitly returned False.
                action_status = getattr(action_result, "status", None)
                action_success = getattr(action_result, "success", None)

                if action_status is not None:
                    consent_action_succeeded = action_status == "SUCCESS"
                elif action_success is not None:
                    consent_action_succeeded = action_success is True
                elif isinstance(action_result, bool):
                    consent_action_succeeded = action_result
                else:
                    consent_action_succeeded = True

                if self.post_action_wait_ms > 0:
                    await self.page.wait_for_timeout(
                        self.post_action_wait_ms
                    )

                final_url = self.page.url
                after_state = await self.collect_current_state(
                    self.page,
                    self.context,
                    final_url,
                )

                # If the click could not be completed, the browser is still
                # considered pre-consent; do not imply that consent was changed.
                after_phase = (
                    "after_consent"
                    if consent_action_succeeded
                    else "before_consent"
                )
                observations.extend(
                    self._copy_with_consent_phase(
                        after_state,
                        after_phase,
                    )
                )

                all_network_observations = network_collector.get_observations()
                network_after_action = all_network_observations[pre_action_count:]
                observations.extend(
                    self._copy_network_with_consent_phase(
                        network_after_action,
                        after_phase,
                        network_request_phases,
                    )
                )
                network_observation_count_recorded = len(
                    all_network_observations
                )

            else:
                # Preserve the existing one-pass behavior: no consent phase
                # is assigned when no consent action was requested.
                observations.extend(
                    await self.collect_current_state(
                        self.page,
                        self.context,
                        final_url,
                    )
                )

                network_observations = network_collector.get_observations()
                observations.extend(network_observations)
                network_observation_count_recorded = len(
                    network_observations
                )

            network_collector.stop_collecting()

            completed_at = time.time()
            return SinglePassResult(
                target_url=validated_url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=completed_at,
                status=CrawlerStatus.COMPLETED,
                action_result=action_result,
            )

        except Exception as exc:
            if network_collector is not None:
                network_collector.stop_collecting()
                remaining_network_observations = (
                    network_collector.get_observations()[
                        network_observation_count_recorded:
                    ]
                )
                if post_navigation_action is not None:
                    remaining_phase = (
                        "after_consent"
                        if consent_action_succeeded
                        else "before_consent"
                    )
                    observations.extend(
                        self._copy_network_with_consent_phase(
                            remaining_network_observations,
                            remaining_phase,
                            network_request_phases,
                        )
                    )
                else:
                    observations.extend(remaining_network_observations)

            completed_at = time.time()
            return SinglePassResult(
                target_url=validated_url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=completed_at,
                status=CrawlerStatus.FAILED,
                action_result=action_result,
                error=(
                    str(exc)
                    if isinstance(exc, URLValidationError)
                    else "Scan failed during navigation or evidence collection."
                ),
            )

        finally:
            if network_collector is not None:
                network_collector.stop_collecting()

    @staticmethod
    async def collect_current_state(
        page: Page,
        context: BrowserContext,
        source_url: str,
    ) -> list[Observation]:
        """
        Collect all standard PrivaCheck observations
        from the current page state.
        """

        dom_collector = DOMCollector(
            page,
            source_url,
        )

        link_collector = LinkCollector(
            page,
            source_url,
        )

        cookie_collector = CookieCollector(
            context,
            source_url,
        )

        storage_collector = StorageCollector(
            page,
            source_url,
        )

        observations: list[Observation] = []

        observations.extend(
            await dom_collector.collect_all()
        )

        observations.extend(
            await link_collector.collect_links()
        )

        observations.extend(
            await cookie_collector.collect()
        )

        observations.extend(
            await storage_collector.collect_all()
        )

        return observations