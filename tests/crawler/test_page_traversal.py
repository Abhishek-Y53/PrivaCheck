import pytest

from backend.crawler import page_traversal
from backend.schemas.core import Observation


class FakePage:
    """Minimal mock of a Playwright page for traversal tests."""

    def __init__(self, links_by_url, texts_by_url):
        self.url = ""
        self.links_by_url = links_by_url
        self.texts_by_url = texts_by_url

    async def goto(self, url, wait_until, timeout):
        self.url = url

    async def wait_for_timeout(self, milliseconds):
        pass

    async def evaluate(self, script):
        return self.texts_by_url.get(self.url, "")

    async def close(self):
        pass


class FakeContext:
    """Creates fake pages without launching a real browser."""

    def __init__(self, links_by_url, texts_by_url):
        self.links_by_url = links_by_url
        self.texts_by_url = texts_by_url
        self.pages = []

    async def new_page(self):
        page = FakePage(
            self.links_by_url,
            self.texts_by_url,
        )
        self.pages.append(page)
        return page


class FakeLinkCollector:
    """Replaces LinkCollector to provide deterministic test links."""

    def __init__(self, page, source_url):
        self.page = page
        self.source_url = source_url

    async def collect_links(self):
        links = self.page.links_by_url.get(
            self.page.url,
            [],
        )

        observations = []

        for link in links:
            href, text = link[0], link[1]
            region = link[2] if len(link) > 2 else "other"

            observations.append(
                Observation(
                    category="link",
                    source_url=self.source_url,
                    timestamp=1.0,
                    data={
                        "href": href,
                        "text": text,
                        "target": "",
                        "region": region,
                        "is_footer_link": region == "footer",
                    },
                )
            )

        return observations


@pytest.mark.asyncio
async def test_traversal_visits_internal_pages_and_collects_text(
    monkeypatch,
):
    root_url = "https://example.com/"
    privacy_url = "https://example.com/privacy"
    rights_url = "https://example.com/rights"
    external_url = "https://other.example/privacy"

    links_by_url = {
        root_url: [
            (privacy_url, "Privacy Policy"),
            (external_url, "External Privacy Policy"),
        ],
        privacy_url: [
            (rights_url, "Your Privacy Rights"),
        ],
    }

    texts_by_url = {
        root_url: "Home page content",
        privacy_url: "Privacy policy and data protection",
    }

    monkeypatch.setattr(
        page_traversal,
        "LinkCollector",
        FakeLinkCollector,
    )

    context = FakeContext(
        links_by_url,
        texts_by_url,
    )

    collector = page_traversal.PageTraversalCollector(
        context=context,
        start_url=root_url,
        max_depth=1,
        max_pages=10,
    )

    observations = await collector.collect()

    visited_urls = [
        page.url
        for page in context.pages
    ]

    # The homepage and its internal privacy page are visited.
    assert visited_urls == [
        root_url,
        privacy_url,
    ]

    # The external website is not visited.
    assert external_url not in visited_urls

    # The depth limit prevents visiting the rights page.
    assert rights_url not in visited_urls

    # Text from both visited pages is collected.
    visible_text = [
        observation
        for observation in observations
        if observation.category == "dom_visible_text"
    ]

    assert len(visible_text) == 2

    assert {
        observation.data["text"]
        for observation in visible_text
    } == {
        "Home page content",
        "Privacy policy and data protection",
    }

    # The privacy link records the depth at which it was found.
    privacy_links = [
        observation
        for observation in observations
        if (
            observation.category == "link"
            and observation.data["href"] == privacy_url
        )
    ]

    assert len(privacy_links) == 1
    assert privacy_links[0].data["crawl_depth"] == 0


@pytest.mark.asyncio
async def test_traversal_respects_max_pages(monkeypatch):
    root_url = "https://example.com/"
    privacy_url = "https://example.com/privacy"
    settings_url = "https://example.com/settings"

    links_by_url = {
        root_url: [
            (privacy_url, "Privacy"),
            (settings_url, "Settings"),
        ],
    }

    texts_by_url = {
        root_url: "Home page",
        privacy_url: "Privacy page",
        settings_url: "Settings page",
    }

    monkeypatch.setattr(
        page_traversal,
        "LinkCollector",
        FakeLinkCollector,
    )

    context = FakeContext(
        links_by_url,
        texts_by_url,
    )

    collector = page_traversal.PageTraversalCollector(
        context=context,
        start_url=root_url,
        max_depth=2,
        max_pages=2,
    )

    await collector.collect()

    # The page cap includes the starting page.
    assert len(context.pages) == 2

    assert [
        page.url
        for page in context.pages
    ] == [
        root_url,
        privacy_url,
    ]


@pytest.mark.asyncio
async def test_traversal_prioritizes_footer_and_keyword_links(
    monkeypatch,
):
    root_url = "https://example.com/"
    article_url = "https://example.com/latest-news"
    contact_url = "https://example.com/contact"
    settings_url = "https://example.com/account-settings"
    privacy_url = "https://example.com/privacy"

    links_by_url = {
        root_url: [
            (article_url, "Latest News", "main"),
            (contact_url, "Contact", "footer"),
            (settings_url, "Account Settings", "main"),
            (privacy_url, "Privacy Policy", "footer"),
        ],
    }

    texts_by_url = {
        root_url: "Homepage",
        privacy_url: "Privacy policy",
        settings_url: "Account settings",
        contact_url: "Contact page",
        article_url: "News article",
    }

    monkeypatch.setattr(
        page_traversal,
        "LinkCollector",
        FakeLinkCollector,
    )

    context = FakeContext(
        links_by_url,
        texts_by_url,
    )

    collector = page_traversal.PageTraversalCollector(
        context=context,
        start_url=root_url,
        max_depth=2,
        max_pages=3,
        priority_keywords=[
            "privacy",
            "settings",
        ],
    )

    await collector.collect()

    visited_urls = [
        page.url
        for page in context.pages
    ]

    # Homepage is visited first, followed by the highest-priority
    # footer privacy link and then the matching settings link.
    assert visited_urls == [
        root_url,
        privacy_url,
        settings_url,
    ]
