import time
from typing import List

from backend.crawler.browser import BrowserManager
from backend.crawler.pass_runner import SinglePassRunner
from backend.schemas.core import CrawlerResult, Observation


class CrawlerOrchestrator:
    """
    Coordinates the normal one-pass crawler workflow.

    The actual single-page crawling logic is implemented
    by SinglePassRunner.
    """

    def __init__(
        self,
        url: str,
        headless: bool = True,
    ):
        self.url = url
        self.headless = headless
        self.browser_manager = BrowserManager(
            headless=headless
        )

    async def run(self) -> CrawlerResult:
        started_at = time.time()

        observations: List[Observation] = []

        context = None
        page = None
        final_url = self.url

        try:
            # Start browser.
            await self.browser_manager.start()

            # Create the normal isolated context and page.
            context, page = (
                await self.browser_manager
                .create_context_and_page()
            )

            # Use shared single-pass implementation.
            pass_runner = SinglePassRunner(
                page,
                context,
                self.url,
                wait_ms=3000,
            )

            result = await pass_runner.run()

            observations.extend(
                result.observations
            )

            final_url = result.final_url

            return CrawlerResult(
                target_url=self.url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=time.time(),
                status=result.status,
                error=result.error,
            )

        except Exception as exc:
            return CrawlerResult(
                target_url=self.url,
                final_url=final_url,
                observations=observations,
                started_at=started_at,
                completed_at=time.time(),
                status="FAILED",
                error=str(exc),
            )

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

            await self.browser_manager.stop()