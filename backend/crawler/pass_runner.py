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

    async def run(
        self,
        post_navigation_action: PostNavigationAction | None = None,
    ) -> SinglePassResult:
        """
        Navigate to the URL, optionally perform an action,
        then collect observations.
        """

        started_at = time.time()
        observations: list[Observation] = []
        final_url = self.url
        action_result: Any = None
        network_collector: NetworkCollector | None = None

        try:
            # Start network collection before navigation.
            network_collector = NetworkCollector(
                self.page,
                self.url,
            )
            network_collector.start_collecting()

            # Navigate.
            await self.page.goto(
                self.url,
                wait_until="domcontentloaded",
            )

            # Allow dynamic page activity to settle.
            await self.page.wait_for_timeout(self.wait_ms)

            final_url = self.page.url

            # Optional action such as Accept or Reject.
            if post_navigation_action is not None:
                action_result = await post_navigation_action(self.page)

                if self.post_action_wait_ms > 0:
                    await self.page.wait_for_timeout(
                        self.post_action_wait_ms
                    )

            # Collect DOM, links, cookies and storage.
            observations.extend(
                await self.collect_current_state(
                    self.page,
                    self.context,
                    final_url,
                )
            )

            # Stop network capture and collect network observations.
            network_collector.stop_collecting()
            observations.extend(
                network_collector.get_observations()
            )

            completed_at = time.time()

            return SinglePassResult(
                target_url=self.url,
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
                observations.extend(
                    network_collector.get_observations()
                )

            completed_at = time.time()

            return SinglePassResult(
                target_url=self.url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=completed_at,
                status=CrawlerStatus.FAILED,
                action_result=action_result,
                error=str(exc),
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