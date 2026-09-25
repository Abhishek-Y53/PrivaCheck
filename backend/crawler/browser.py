from typing import Tuple

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)


class BrowserManager:
    """
    Responsible exclusively for browser lifecycle.

    It does not collect observations or perform compliance analysis.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        """Start Playwright and launch Chromium."""

        self._playwright = (
            await async_playwright().start()
        )

        self._browser = (
            await self._playwright.chromium.launch(
                headless=self.headless
            )
        )

    async def create_context_and_page(
        self,
    ) -> Tuple[BrowserContext, Page]:
        """
        Create a fresh isolated browser context and page.
        """

        if self._browser is None:
            raise RuntimeError(
                "Browser is not started. "
                "Call start() first."
            )

        context = (
            await self._browser.new_context()
        )

        page = await context.new_page()

        return context, page

    async def stop(self) -> None:
        """Safely close browser and Playwright."""

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None