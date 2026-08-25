import asyncio
from typing import Tuple
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

class BrowserManager:
    """
    Responsible exclusively for the browser lifecycle.
    Does NOT collect data or run scans directly.
    """
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        """
        Starts the playwright engine and launches the browser.
        """
        print("Starting browser...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

    async def create_context_and_page(self) -> Tuple[BrowserContext, Page]:
        """
        Creates a new isolated browser context and page.
        Returns both so that collectors have access to context-level data (like cookies).
        """
        if not self._browser:
            raise RuntimeError("Browser is not started. Call start() first.")
        
        context = await self._browser.new_context()
        page = await context.new_page()
        return context, page

    async def stop(self) -> None:
        """
        Safely closes the browser and playwright engine.
        """
        print("Stopping browser...")
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# --- Test Script ---
if __name__ == "__main__":
    from backend.crawler.two_pass import TwoPassRunner

    async def test():
        manager = BrowserManager(headless=True)
        await manager.start()
        
        context, page = await manager.create_context_and_page()
        url = "https://www.mstcecommerce.com/auctionhome/index_new.jsp"
        
        print(f"\nRunning Two-Pass Scan on {url}...")
        runner = TwoPassRunner(page, context, url)
        observations = await runner.run()
        
        print(f"\nTotal Observations Collected: {len(observations)}")
        if observations:
            print(f"Example Observation: {observations[0].category}")
        
        await page.close()
        await context.close()
        await manager.stop()

    asyncio.run(test())
