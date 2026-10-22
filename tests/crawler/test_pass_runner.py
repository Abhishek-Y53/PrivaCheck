"""Unit tests for the consent-aware, security-hardened SinglePassRunner."""

import pytest

from backend.crawler import pass_runner as pass_runner_module
from backend.crawler.pass_runner import SinglePassRunner
from backend.schemas.core import CrawlerStatus, Observation


class FakeContext:
    """Minimal BrowserContext fake supporting required routing APIs."""

    def __init__(self):
        self.http_routes = []
        self.websocket_routes = []

    @property
    def routes_installed(self):
        return bool(self.http_routes) and bool(self.websocket_routes)

    async def route(self, pattern, handler):
        assert pattern == "**/*"
        self.http_routes.append((pattern, handler))

    async def route_web_socket(self, pattern, handler):
        assert pattern == "**/*"
        self.websocket_routes.append((pattern, handler))


class FakePage:
    """Minimal Page fake; it never opens a real network connection."""

    def __init__(self, context):
        self.context = context
        self.url = "about:blank"
        self.goto_calls = []
        self._listeners = {}

    def on(self, event, handler):
        self._listeners.setdefault(event, []).append(handler)

    def remove_listener(self, event, handler):
        listeners = self._listeners.get(event, [])
        if handler in listeners:
            listeners.remove(handler)

    async def goto(self, url, wait_until, timeout):
        # Security hooks must be installed before navigation.
        assert self.context.routes_installed
        assert wait_until == "domcontentloaded"
        assert timeout == 30_000

        self.goto_calls.append(url)
        self.url = url

    async def wait_for_timeout(self, _milliseconds):
        return None


class FakeNetworkCollector:
    """Deterministic replacement; no network I/O occurs."""

    def __init__(self, _page, source_url):
        self.observations = [
            Observation(
                category="network_request",
                source_url=source_url,
                timestamp=1.0,
                data={
                    "request_id": "test-request-1",
                    "url": source_url,
                    "method": "GET",
                },
            )
        ]
        self.started = False
        self.stop_calls = 0

    def start_collecting(self):
        self.started = True

    def stop_collecting(self):
        self.stop_calls += 1

    def get_observations(self):
        return list(self.observations)


@pytest.mark.asyncio
async def test_single_pass_runs_navigation_action_and_collection(monkeypatch):
    """A successful pass installs guards, captures both phases, and returns."""

    async def fake_validate_public_http_url(url):
        # Isolate this unit test from DNS. Actual URL/DNS policy is tested
        # separately in tests/security.
        assert url == "https://example.com"
        return url

    monkeypatch.setattr(
        pass_runner_module,
        "validate_public_http_url",
        fake_validate_public_http_url,
    )

    monkeypatch.setattr(
        pass_runner_module,
        "NetworkCollector",
        FakeNetworkCollector,
    )

    expected = Observation(
        category="test_snapshot",
        source_url="https://example.com/",
        timestamp=1.0,
        data={"ok": True},
    )

    async def fake_collect_current_state(page, context, source_url):
        assert page.url == source_url
        return [expected]

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
        "https://example.com",
        wait_ms=0,
    )

    async def action(_page):
        return "done"

    result = await runner.run(post_navigation_action=action)

    # The pass completes and returns the expected navigation/action result.
    assert result.status == CrawlerStatus.COMPLETED
    assert result.error is None
    assert result.target_url == "https://example.com"
    assert result.final_url == "https://example.com"
    assert result.action_result == "done"
    assert page.goto_calls == ["https://example.com"]

    # Both security hooks are installed before the page navigates.
    assert len(context.http_routes) == 1
    assert len(context.websocket_routes) == 1
    assert context.http_routes[0][0] == "**/*"
    assert context.websocket_routes[0][0] == "**/*"

    # The snapshot is captured before and after the action.
    snapshots = [
        observation
        for observation in result.observations
        if observation.category == "test_snapshot"
    ]

    assert len(snapshots) == 2

    assert [
        observation.data["consent_phase"]
        for observation in snapshots
    ] == [
        "before_consent",
        "after_consent",
    ]

    assert all(
        observation.data["ok"] is True
        for observation in snapshots
    )

    # The network observation was captured before the action.
    network_observations = [
        observation
        for observation in result.observations
        if observation.category == "network_request"
    ]

    assert len(network_observations) == 1
    assert (
        network_observations[0].data["consent_phase"]
        == "before_consent"
    )

    # Phase tagging must not mutate the original collected observation.
    assert expected.data == {"ok": True}