from types import SimpleNamespace

import pytest

from backend.crawler import pass_runner as pass_runner_module
from backend.crawler.pass_runner import SinglePassRunner
from backend.schemas.core import CrawlerStatus, Observation


class FakePage:
    def __init__(self, context):
        self.context = context
        self.url = "about:blank"
        self.goto_calls = []

    async def goto(self, url, wait_until, timeout):
        assert self.context.routes_installed
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_timeout(self, _milliseconds):
        return None


class FakeContext:
    def __init__(self):
        self.routes_installed = False
        self.http_handler = None
        self.websocket_handler = None

    async def route(self, pattern, handler):
        assert pattern == "**/*"
        self.http_handler = handler
        self._mark_installed()

    async def route_web_socket(self, pattern, handler):
        assert pattern == "**/*"
        self.websocket_handler = handler
        self._mark_installed()

    def _mark_installed(self):
        self.routes_installed = (
            self.http_handler is not None and self.websocket_handler is not None
        )


class FakeNetworkCollector:
    def __init__(self, _page, source_url):
        self.observations = [
            Observation(
                category="network_request",
                source_url=source_url,
                timestamp=1.0,
                data={"request_id": "req-1", "url": source_url},
            )
        ]

    def start_collecting(self):
        pass

    def stop_collecting(self):
        pass

    def get_observations(self):
        return self.observations


@pytest.mark.asyncio
async def test_runner_installs_http_and_websocket_guards_before_navigation(monkeypatch):
    async def allow_test_url(url):
        return url

    monkeypatch.setattr(pass_runner_module, "validate_public_http_url", allow_test_url)
    monkeypatch.setattr(pass_runner_module, "NetworkCollector", FakeNetworkCollector)

    async def fake_collect_current_state(_page, _context, source_url):
        return [
            Observation(
                category="dom_visible_text",
                source_url=source_url,
                timestamp=1.0,
                data={"text": "test state"},
            )
        ]

    monkeypatch.setattr(
        SinglePassRunner,
        "collect_current_state",
        staticmethod(fake_collect_current_state),
    )

    context = FakeContext()
    page = FakePage(context)
    runner = SinglePassRunner(
        page,
        context,
        "https://example.com/",
        wait_ms=0,
        post_action_wait_ms=0,
    )

    async def successful_action(_page):
        return SimpleNamespace(status="SUCCESS", success=True)

    result = await runner.run(post_navigation_action=successful_action)

    assert result.status == CrawlerStatus.COMPLETED
    assert context.http_handler is not None
    assert context.websocket_handler is not None
    assert page.goto_calls == ["https://example.com/"]

    dom_phases = [
        item.data.get("consent_phase")
        for item in result.observations
        if item.category == "dom_visible_text"
    ]
    assert dom_phases == ["before_consent", "after_consent"]

    network_phases = [
        item.data.get("consent_phase")
        for item in result.observations
        if item.category == "network_request"
    ]
    assert network_phases == ["before_consent"]


@pytest.mark.asyncio
async def test_runner_rejects_loopback_before_navigation_without_echoing_input():
    context = FakeContext()
    page = FakePage(context)
    raw_url = "http://127.0.0.1/admin"

    result = await SinglePassRunner(page, context, raw_url, wait_ms=0).run()

    assert result.status == CrawlerStatus.FAILED
    assert page.goto_calls == []
    assert not context.routes_installed
    assert result.target_url == ""
    assert result.final_url == ""
    assert "127.0.0.1" not in (result.error or "")
