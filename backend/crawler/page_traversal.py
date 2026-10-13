
from __future__ import annotations

import heapq
import itertools
import time
from typing import List
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page

from backend.crawler.links import LinkCollector
from backend.schemas.core import Observation


class PageTraversalCollector:
    """
    Generic priority-based same-host page traversal collector.

    Responsibilities:
    - Discover links from visited pages.
    - Prioritize links using configurable keywords and page regions.
    - Traverse internal pages up to a configurable depth.
    - Limit the number of visited pages.
    - Collect link observations and visible page text.

    This class gathers observations. It does not evaluate compliance.
    """

    def __init__(
        self,
        context: BrowserContext,
        start_url: str,
        max_depth: int = 2,
        max_pages: int = 10,
        priority_keywords: List[str] | None = None,
    ):
        self.context = context
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages

        self.priority_keywords = tuple(
            keyword.strip().casefold()
            for keyword in (priority_keywords or [])
            if keyword.strip()
        )

        self._visited: set[str] = set()

    async def collect(self) -> List[Observation]:
        """
        Traverse pages using a priority queue.

        Link priority:
        1. Footer links matching configured keywords.
        2. Other links matching configured keywords.
        3. Other footer links.
        4. Remaining links.

        Higher-priority pages can be visited before lower-priority
        pages discovered earlier, subject to depth and page limits.
        """

        observations: List[Observation] = []

        normalized_start = self._normalize_url(self.start_url)

        if not normalized_start:
            return observations

        start_hostname = urlparse(normalized_start).hostname

        # Queue entries contain:
        # (-priority, depth, sequence_number, URL)
        #
        # The sequence number preserves deterministic ordering
        # when candidates have equal priority and depth.
        frontier: list[tuple[int, int, int, str]] = []
        sequence = itertools.count()

        initial_priority = 5

        heapq.heappush(
            frontier,
            (
                -initial_priority,
                0,
                next(sequence),
                normalized_start,
            ),
        )

        # Remember the best queued priority/depth for each URL.
        # This lets a better-discovered link replace a lower-priority
        # queued entry without creating duplicate visits.
        queued_rank: dict[str, tuple[int, int]] = {
            normalized_start: (initial_priority, 0)
        }

        while frontier and len(self._visited) < self.max_pages:
            negative_priority, depth, _, current_url = (
                heapq.heappop(frontier)
            )

            normalized_url = self._normalize_url(current_url)

            if not normalized_url:
                continue

            priority = -negative_priority

            # Ignore outdated queue entries superseded by a better
            # priority or a shallower route to the same URL.
            if queued_rank.get(normalized_url) != (priority, depth):
                continue

            queued_rank.pop(normalized_url, None)

            if normalized_url in self._visited:
                continue

            if not self._is_same_origin(
                normalized_url,
                start_hostname,
            ):
                continue

            # Count attempted visits against the page budget too,
            # so repeatedly failing pages cannot cause unlimited work.
            self._visited.add(normalized_url)

            page: Page | None = None

            try:
                page = await self.context.new_page()

                await page.goto(
                    normalized_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                await page.wait_for_timeout(1000)

                final_url = page.url

                # Collect links from this page.
                link_collector = LinkCollector(
                    page,
                    final_url,
                )

                page_links = await link_collector.collect_links()

                for observation in page_links:
                    observation.data["crawl_depth"] = depth
                    observations.append(observation)

                # Collect visible text from this page.
                visible_text = await page.evaluate(
                    """
                    () => {
                        if (!document.body) {
                            return "";
                        }

                        return document.body.innerText
                            .replace(/\\s+/g, " ")
                            .trim();
                    }
                    """
                )

                if visible_text:
                    observations.append(
                        Observation(
                            category="dom_visible_text",
                            source_url=final_url,
                            timestamp=time.time(),
                            data={
                                "text": visible_text,
                                "crawl_depth": depth,
                            },
                        )
                    )

                # Do not discover another level beyond max_depth.
                if depth >= self.max_depth:
                    continue

                # Rank links before adding eligible destinations
                # to the global priority queue.
                ranked_links = sorted(
                    page_links,
                    key=self._link_priority,
                    reverse=True,
                )

                for observation in ranked_links:
                    href = observation.data.get("href")

                    if not isinstance(href, str):
                        continue

                    next_url = self._normalize_url(href)

                    if not next_url:
                        continue

                    if not self._is_same_origin(
                        next_url,
                        start_hostname,
                    ):
                        continue

                    if next_url in self._visited:
                        continue

                    candidate_priority = self._link_priority(
                        observation
                    )
                    candidate_depth = depth + 1

                    existing_rank = queued_rank.get(next_url)

                    if existing_rank is not None:
                        existing_priority, existing_depth = (
                            existing_rank
                        )

                        # Keep the better priority. For equal
                        # priorities, prefer the shallower route.
                        if candidate_priority < existing_priority:
                            continue

                        if (
                            candidate_priority == existing_priority
                            and candidate_depth >= existing_depth
                        ):
                            continue

                    queued_rank[next_url] = (
                        candidate_priority,
                        candidate_depth,
                    )

                    heapq.heappush(
                        frontier,
                        (
                            -candidate_priority,
                            candidate_depth,
                            next(sequence),
                            next_url,
                        ),
                    )

            except Exception:
                # An inaccessible page should not stop the crawl.
                continue

            finally:
                if page is not None:
                    try:
                        await page.close()
                    except Exception:
                        pass

        return observations

    def _link_priority(self, observation: Observation) -> int:
        """
        Assign a priority based on configured keywords and the
        region metadata collected by LinkCollector.
        """

        data = observation.data

        text = data.get("text", "")
        href = data.get("href", "")

        if not isinstance(text, str):
            text = ""

        if not isinstance(href, str):
            href = ""

        searchable_text = f"{text} {href}".casefold()

        matches_keyword = any(
            keyword in searchable_text
            for keyword in self.priority_keywords
        )

        is_footer = (
            data.get("is_footer_link") is True
            or data.get("region") == "footer"
        )

        if is_footer and matches_keyword:
            return 4

        if matches_keyword:
            return 3

        if is_footer:
            return 2

        return 1

    @staticmethod
    def _normalize_url(url: str) -> str | None:
        """
        Normalize URLs and reject non-HTTP(S) schemes.
        """

        try:
            parsed = urlparse(url)

            if parsed.scheme.lower() not in {"http", "https"}:
                return None

            if not parsed.netloc:
                return None

            # Treat URL fragments as the same page.
            return parsed._replace(fragment="").geturl()

        except Exception:
            return None

    @staticmethod
    def _is_same_origin(
        url: str,
        hostname: str | None,
    ) -> bool:
        """
        Restrict traversal to the target hostname.
        """

        if hostname is None:
            return False

        try:
            return urlparse(url).hostname == hostname
        except Exception:
            return False
