import time
from typing import List

from playwright.async_api import Page

from backend.schemas.core import Observation


class LinkCollector:
    """
    Collects link data required by the crawler.

    Responsible only for discovering links and their metadata.
    Does not perform navigation or compliance analysis.
    """

    def __init__(self, page: Page, source_url: str):
        self.page = page
        self.source_url = source_url

    async def collect_links(self) -> List[Observation]:
        """
        Collect all links with their destination and identifying text.
        """

        links = await self.page.evaluate(
            """
            () => {
                return Array.from(
                    document.querySelectorAll("a[href]")
                ).map(link => ({
                    href: link.href,
                    text: link.innerText.trim(),
                    aria_label: link.getAttribute("aria-label")
                }));
            }
            """
        )

        observations: List[Observation] = []

        for link in links:
            observations.append(
                Observation(
                    category="link",
                    source_url=self.source_url,
                    timestamp=time.time(),
                    data=link
                )
            )

        return observations