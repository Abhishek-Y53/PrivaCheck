
import time
from typing import List

from playwright.async_api import Page

from backend.schemas.core import Observation


class LinkCollector:
    """
    Collects link information and surrounding page context.

    This collector records evidence only. It does not determine
    compliance or decide which links to visit.
    """

    def __init__(self, page: Page, source_url: str):
        self.page = page
        self.source_url = source_url

    async def collect_links(self) -> List[Observation]:
        observations: List[Observation] = []

        links = await self.page.evaluate(
            """
            () => {
                function getRegion(link) {
                    if (
                        link.closest(
                            'footer, [role="contentinfo"], ' +
                            '#footer, .footer, ' +
                            '[id*="footer" i], [class*="footer" i]'
                        )
                    ) {
                        return "footer";
                    }

                    if (
                        link.closest(
                            'header, [role="banner"], ' +
                            '#header, .header, ' +
                            '[id*="header" i], [class*="header" i]'
                        )
                    ) {
                        return "header";
                    }

                    if (
                        link.closest(
                            'main, [role="main"], ' +
                            '#main, .main-content, ' +
                            '[id*="main-content" i]'
                        )
                    ) {
                        return "main";
                    }

                    return "other";
                }

                function getContextText(link) {
                    // Prefer a nearby text container rather than the
                    // entire section or entire page.
                    const container = link.closest(
                        'p, li, dd, td, section, article'
                    ) || link.parentElement;

                    if (!container) {
                        return "";
                    }

                    return (container.innerText || "")
                        .replace(/\\s+/g, " ")
                        .trim()
                        .slice(0, 500);
                }

                return Array.from(
                    document.querySelectorAll('a[href]')
                ).map(a => {
                    const region = getRegion(a);

                    return {
                        href: a.href,
                        text: a.innerText.trim(),
                        target: a.target,
                        region: region,
                        is_footer_link: region === "footer",
                        context_text: getContextText(a)
                    };
                });
            }
            """
        )

        for link in links:
            observations.append(
                Observation(
                    category="link",
                    source_url=self.source_url,
                    timestamp=time.time(),
                    data=link,
                )
            )

        return observations
