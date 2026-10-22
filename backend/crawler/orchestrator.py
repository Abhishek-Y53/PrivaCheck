import logging
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
from backend.security.url_validation import (
    PublicNetworkGuard,
    URLValidationError,
    normalize_http_url,
    validate_public_http_url,
)


logger = logging.getLogger(__name__)


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

        final_url = ""
        validated_url = ""
        stage = "initialization"

        try:
            # --------------------------------------------------
            # 1. Validate the supplied URL.
            # --------------------------------------------------

            # Reject malformed schemes, credentials, unsupported
            # ports, and non-public IP literals before launching
            # the browser.
            stage = "URL normalization"
            validated_url = normalize_http_url(self.url)

            # --------------------------------------------------
            # 2. Start browser and create an isolated context.
            # --------------------------------------------------

            stage = "browser startup"
            await self.browser_manager.start()

            stage = "browser context and page creation"
            context, page = (
                await self.browser_manager.create_context_and_page()
            )

            # --------------------------------------------------
            # 3. Install the HTTP and WebSocket security guard.
            # --------------------------------------------------

            # Install the guard before making any network request.
            # The guard also applies to pages opened during traversal.
            stage = "security guard installation"

            request_guard = PublicNetworkGuard()
            await request_guard.install(context)

            # Re-resolve and validate the target immediately before
            # navigation to reduce DNS-rebinding risk.
            stage = "public target validation"
            validated_url = await validate_public_http_url(
                validated_url
            )

            # --------------------------------------------------
            # 4. Start network collection before navigation.
            # --------------------------------------------------

            stage = "network collector initialization"

            network_collector = NetworkCollector(
                page,
                validated_url,
            )
            network_collector.start_collecting()

            # --------------------------------------------------
            # 5. Navigate to the target website.
            # --------------------------------------------------

            stage = "initial page navigation"

            await page.goto(
                validated_url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            # Allow dynamically loaded content some time to appear.
            stage = "waiting for dynamic content"
            await page.wait_for_timeout(3000)

            final_url = page.url

            # --------------------------------------------------
            # 6. Collect observations from the initial page.
            # --------------------------------------------------

            dom_collector = DOMCollector(page, final_url)
            link_collector = LinkCollector(page, final_url)
            cookie_collector = CookieCollector(context, final_url)
            storage_collector = StorageCollector(page, final_url)
            tls_collector = TLSCollector()

            stage = "DOM observation collection"
            dom_observations = await dom_collector.collect_all()

            # Preserve homepage link observations separately.
            stage = "homepage link collection"

            link_observations = (
                await link_collector.collect_links()
            )

            # Mark homepage links with crawl depth 0.
            for observation in link_observations:
                observation.data.setdefault("crawl_depth", 0)

            stage = "cookie collection"
            cookie_observations = (
                await cookie_collector.collect()
            )

            stage = "storage collection"
            storage_observations = (
                await storage_collector.collect_all()
            )

            # --------------------------------------------------
            # 7. Traverse eligible internal pages.
            # --------------------------------------------------
            #
            # Limits:
            #   Maximum depth: 2
            #   Maximum visited pages: 10
            #
            # Traversal is an additional capability. If it fails,
            # retain the observations already collected from the
            # initial page.

            traversal_observations: List[Observation] = []

            try:
                stage = "internal page traversal"

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

            except Exception:
                # Log the full traceback in the server console.
                # Do not discard observations from the initial page.
                logger.exception(
                    "Page traversal failed; preserving initial-page "
                    "observations"
                )

            # The standalone LinkCollector already collected
            # homepage links. Remove duplicate depth-0 links from
            # the traversal results.
            traversal_observations = [
                observation
                for observation in traversal_observations
                if not (
                    observation.category == "link"
                    and observation.data.get("crawl_depth") == 0
                )
            ]

            # --------------------------------------------------
            # 8. Build page-level context for the initial page.
            # --------------------------------------------------

            page_context_observation = (
                self._build_page_context_observation(
                    final_url,
                    dom_observations,
                )
            )

            # --------------------------------------------------
            # 9. Collect TLS evidence.
            # --------------------------------------------------

            # TLSCollector makes its own outbound connection outside
            # Playwright routing. Validate the final URL again first.
            #
            # Production network egress restrictions are still needed
            # to address DNS validation-to-connection race conditions.

            stage = "TLS evidence collection"

            await validate_public_http_url(final_url)

            tls_observation = tls_collector.verify(
                final_url,
                source_url=final_url,
            )

            # --------------------------------------------------
            # 10. Finish network collection.
            # --------------------------------------------------

            stage = "network observation collection"

            network_collector.stop_collecting()

            network_observations = (
                network_collector.get_observations()
            )

            # --------------------------------------------------
            # 11. Combine all observations.
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

            # --------------------------------------------------
            # 12. Return the completed crawler result.
            # --------------------------------------------------

            stage = "building crawler result"
            completed_at = time.time()

            return CrawlerResult(
                target_url=validated_url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=completed_at,
                status="COMPLETED",
            )

        except Exception as e:
            # Record the underlying exception and traceback in the
            # server logs, together with the stage that was running.
            #
            # Unexpected exception details are not returned to the
            # API caller. URL validation errors retain their existing
            # specific error behavior.

            logger.exception(
                "Crawler failed during stage: %s",
                stage,
            )

            completed_at = time.time()

            return CrawlerResult(
                target_url=validated_url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=completed_at,
                status="FAILED",
                error=(
                    str(e)
                    if isinstance(e, URLValidationError)
                    else (
                        "Scan failed during navigation, traversal, "
                        "or evidence collection."
                    )
                ),
            )

        finally:
            # --------------------------------------------------
            # 13. Clean up browser resources safely.
            # --------------------------------------------------
            #
            # Cleanup failures are logged but should not replace
            # the crawler result or mask the original exception.

            if network_collector is not None:
                try:
                    network_collector.stop_collecting()
                except Exception:
                    logger.exception(
                        "Failed to stop network collection cleanly"
                    )

            if page is not None:
                try:
                    await page.close()
                except Exception:
                    logger.exception(
                        "Failed to close the initial page cleanly"
                    )

            if context is not None:
                try:
                    await context.close()
                except Exception:
                    logger.exception(
                        "Failed to close the browser context cleanly"
                    )

            try:
                await self.browser_manager.stop()
            except Exception:
                logger.exception(
                    "Failed to stop the browser cleanly"
                )