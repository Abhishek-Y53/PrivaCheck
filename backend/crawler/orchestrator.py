
import time
from typing import List
from urllib.parse import urlparse

from backend.crawler.browser import BrowserManager
from backend.crawler.network import NetworkCollector
from backend.crawler.cookies import CookieCollector
from backend.crawler.storage import StorageCollector
from backend.crawler.dom import DOMCollector
from backend.crawler.links import LinkCollector
from backend.crawler.page_traversal import PageTraversalCollector
from backend.crawler.tls import TLSCollector
from backend.schemas.core import Observation, CrawlerResult


class CrawlerOrchestrator:
    """
    Coordinates the crawler components.

    Responsible for:
    - Browser lifecycle
    - Page navigation
    - Starting/stopping network collection
    - Running individual collectors
    - Traversing internal pages
    - Collecting generic TLS verification evidence
    - Collecting generic page-level context
    - Combining observations

    Does not perform compliance analysis.
    """

    def __init__(self, url: str, headless: bool = True):
        self.url = url
        self.headless = headless
        self.browser_manager = BrowserManager(headless=headless)

    @staticmethod
    def _build_page_context_observation(
        final_url: str,
        dom_observations: List[Observation],
    ) -> Observation:
        """
        Build generic page-level context from the final URL
        and collected DOM observations.

        This method only records facts. It does not evaluate
        compliance.
        """

        parsed_final_url = urlparse(final_url)

        form_count = sum(
            1
            for observation in dom_observations
            if observation.category == "dom_form"
        )

        return Observation(
            category="page_context",
            source_url=final_url,
            timestamp=time.time(),
            data={
                "final_url": final_url,
                "protocol": parsed_final_url.scheme,
                "is_https": (
                    parsed_final_url.scheme.lower() == "https"
                ),
                "has_forms": form_count > 0,
                "form_count": form_count,
            },
        )

    async def run(self) -> CrawlerResult:
        started_at = time.time()
        observations: List[Observation] = []

        context = None
        page = None
        network_collector = None
        final_url = self.url

        try:
            # Start browser.
            await self.browser_manager.start()

            # Create isolated browser context and initial page.
            context, page = (
                await self.browser_manager.create_context_and_page()
            )

            # Start network collection BEFORE navigation.
            network_collector = NetworkCollector(page, self.url)
            network_collector.start_collecting()

            # Navigate to the target website.
            await page.goto(
                self.url,
                wait_until="domcontentloaded",
            )

            # Give dynamically loaded content some time to appear.
            await page.wait_for_timeout(3000)

            # Use the final URL after redirects.
            final_url = page.url

            # --------------------------------------------------
            # 1. Collect observations from the initial page.
            # --------------------------------------------------

            dom_collector = DOMCollector(page, final_url)
            link_collector = LinkCollector(page, final_url)
            cookie_collector = CookieCollector(context, final_url)
            storage_collector = StorageCollector(page, final_url)
            tls_collector = TLSCollector()

            dom_observations = await dom_collector.collect_all()

            # Preserve all original homepage link observations.
            link_observations = (
                await link_collector.collect_links()
            )
            # Mark original homepage links with crawl depth 0.
            for observation in link_observations:
                observation.data.setdefault("crawl_depth", 0)

            cookie_observations = (
                await cookie_collector.collect()
            )

            storage_observations = (
                await storage_collector.collect_all()
            )

            # --------------------------------------------------
            # 2. Traverse internal pages.
            # --------------------------------------------------
            #
            # This collects links and visible text from the
            # homepage and eligible internal pages.
            #
            # The standalone LinkCollector above is retained so
            # the original homepage links remain available even
            # if traversal fails.
            #
            # Limits:
            #   Maximum depth: 2
            #   Maximum visited pages: 10

            traversal_observations: List[Observation] = []

            try:
                traversal_collector = PageTraversalCollector(
                context=context,
                start_url=final_url,
                max_depth=2,
                max_pages=10,
                priority_keywords=[
        # Privacy notices and consent
                "privacy",
                "cookie",
                "consent",
                "data protection",

        # Data subject rights
                "personal data",
        "data access",
        "subject access",
        "data rights",
        "dsar",
        "rectification",

        # Data export and deletion
        "export data",
        "download data",
        "delete data",
        "delete account",
        "erase data",
        "data deletion",

        # Account and privacy settings
        "settings",
        "account",
        "preferences",
    ],
)

                traversal_observations = (
                    await traversal_collector.collect()
                )

            except Exception as traversal_error:
                # Traversal is an additional capability.
                # A traversal failure should not discard the
                # observations already collected from the
                # initial page.
                print(
                    "Page traversal failed:",
                    str(traversal_error),
                )

            # The traversal also collects homepage links.
            # Remove those depth-0 link observations because the
            # standalone LinkCollector already collected them.
            #
            # Keep:
            # - The original homepage links.
            # - Links discovered on child pages.
            # - Visible text from every successfully visited page.

            traversal_observations = [
                observation
                for observation in traversal_observations
                if not (
                    observation.category == "link"
                    and observation.data.get("crawl_depth") == 0
                )
            ]

            # --------------------------------------------------
            # 3. Build page-level context for the initial page.
            # --------------------------------------------------
            #
            # Page context remains based on the initial page.
            # We do not mix form counts from child pages into it.

            page_context_observation = (
                self._build_page_context_observation(
                    final_url,
                    dom_observations,
                )
            )

            # --------------------------------------------------
            # 4. Collect TLS evidence for the initial page.
            # --------------------------------------------------

            tls_observation = tls_collector.verify(
                final_url,
                source_url=final_url,
            )

            # --------------------------------------------------
            # 5. Finish network collection for the initial page.
            # --------------------------------------------------
            #
            # NetworkCollector is attached to the initial page.
            # Network observations from traversal pages are not
            # collected by this existing collector.

            network_collector.stop_collecting()

            network_observations = (
                network_collector.get_observations()
            )

            # --------------------------------------------------
            # 6. Combine all observations.
            # --------------------------------------------------

            observations.extend(dom_observations)

            # Original homepage links.
            observations.extend(link_observations)

            # Child-page links and visible-text observations.
            observations.extend(traversal_observations)

            observations.extend(cookie_observations)
            observations.extend(storage_observations)
            observations.extend(network_observations)

            observations.append(page_context_observation)
            observations.append(tls_observation)

            completed_at = time.time()

            return CrawlerResult(
                target_url=self.url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=completed_at,
                status="COMPLETED",
            )

        except Exception as e:
            completed_at = time.time()

            return CrawlerResult(
                target_url=self.url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=completed_at,
                status="FAILED",
                error=str(e),
            )

        finally:
            # Ensure network listeners are removed.
            if network_collector is not None:
                network_collector.stop_collecting()

            # Close the initial page.
            if page is not None:
                await page.close()

            # Close the browser context, including traversal pages.
            if context is not None:
                await context.close()

            # Stop the browser.
            await self.browser_manager.stop()
