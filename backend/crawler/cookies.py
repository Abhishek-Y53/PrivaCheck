import time
from typing import List
from playwright.async_api import BrowserContext
from backend.schemas.core import Observation

class CookieCollector:
    """
    Collector responsible for extracting cookies from the browser context.
    Adheres to SOC by only extracting raw cookie data without analyzing it.
    """
    def __init__(self, context: BrowserContext, source_url: str):
        self.context = context
        self.source_url = source_url

    async def collect(self) -> List[Observation]:
        """
        Retrieves all cookies currently present in the browser context.
        """
        observations: List[Observation] = []
        cookies = await self.context.cookies()
        
        for cookie in cookies:
            observations.append(
                Observation(
                    category="cookie",
                    source_url=self.source_url,
                    timestamp=time.time(),
                    data=cookie
                )
            )
            
        return observations
