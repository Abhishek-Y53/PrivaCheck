import asyncio
from typing import Dict, Any, List
from playwright.async_api import async_playwright, Browser, Page, Playwright
import time
from backend.schemas.core import Observation

class BrowserManager:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        """Starts the playwright engine and launches the browser."""
        print("Starting browser...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

    async def create_page(self) -> Page:
        """Creates a new browser tab/context."""
        if not self._browser:
            raise RuntimeError("Browser is not started. Call start() first.")
        
        # We create a new context (like an incognito window) for every scan
        context = await self._browser.new_context()
        page = await context.new_page()
        return page

    async def stop(self) -> None:
        """Safely closes the browser and playwright engine."""
        print("Stopping browser...")
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def collect_evidence(self, url: str) -> List[Observation]:
        """Navigates to a URL and collects network and cookie observations."""
        if not self._browser:
            raise RuntimeError("Browser is not started.")
            
        page = await self.create_page()
        observations: List[Observation] = []
        
        # 1. Listen for network requests and turn them into Observations
        page.on(
            "request", 
            lambda req: observations.append(
                Observation(
                    category="network_request",
                    source_url=url,
                    timestamp=time.time(),
                    data={"url": req.url, "method": req.method, "resource_type": req.resource_type}
                )
            )
        )

        print(f"Scanning {url}...")
        await page.goto(url)
        await page.wait_for_timeout(2000) # Wait for trackers to fire
        
        # 2. Collect cookies and turn them into Observations
        cookies = await page.context.cookies()
        for cookie in cookies:
            observations.append(
                Observation(
                    category="cookie",
                    source_url=url,
                    timestamp=time.time(),
                    data=cookie # The raw cookie dictionary
                )
            )
            
        await page.close()
        return observations


# --- Advanced Test Script ---
if __name__ == "__main__":
    async def test():
        manager = BrowserManager(headless=True)
        await manager.start()
        
        # Now we just call our clean, structured method!
        evidence = await manager.collect_evidence("https://www.bbc.com/sport/formula1")
        
        print("\n--- STRUCTURED SCAN RESULTS ---")
        print(f"Total Observations Collected: {len(evidence)}")
        
        # Let's print the first network observation and first cookie observation
        network_obs = [obs for obs in evidence if obs.category == "network_request"]
        cookie_obs = [obs for obs in evidence if obs.category == "cookie"]
        
        print(f"\nExample Network Observation:\n{network_obs[0].model_dump_json(indent=2)}")
        if cookie_obs:
            print(f"\nExample Cookie Observation:\n{cookie_obs[0].model_dump_json(indent=2)}")
        
        await manager.stop()

    asyncio.run(test())
