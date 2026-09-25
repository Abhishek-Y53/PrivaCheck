import pytest

from backend.crawler import pass_runner as pass_runner_module
from backend.crawler.pass_runner import SinglePassRunner
from backend.schemas.core import (
    CrawlerStatus,
    Observation,
)


class FakePage:
    def __init__(self):
        self.url = "https://example.com/"

    async def goto(self, url, wait_until):
        self.url = url

    async def wait_for_timeout(self, ms):
        pass


class FakeContext:
    pass


class FakeNetworkCollector:
    def __init__(self, page, source_url):
        self.observations = [
            Observation(
                category="network_request",
                source_url=source_url,
                timestamp=1.0,
                data={
                    "url": (
                        "https://example.com"
                    )
                },
            )
        ]

    def start_collecting(self):
        pass

    def stop_collecting(self):
        pass

    def get_observations(self):
        return self.observations


@pytest.mark.asyncio
async def test_single_pass_runs_navigation_action_and_collection(
    monkeypatch,
):

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

    async def fake_collect_current_state(
        page,
        context,
        source_url,
    ):
        return [expected]

    monkeypatch.setattr(
        SinglePassRunner,
        "collect_current_state",
        staticmethod(
            fake_collect_current_state
        ),
    )

    page = FakePage()

    runner = SinglePassRunner(
        page,
        FakeContext(),
        "https://example.com",
        wait_ms=0,
    )

    async def action(page):
        return "done"

    result = await runner.run(
        post_navigation_action=action
    )

    assert (
        result.status
        == CrawlerStatus.COMPLETED
    )

    assert (
        result.final_url
        == "https://example.com"
    )

    assert result.action_result == "done"

    assert len(result.observations) == 2

    assert (
        result.observations[0]
        == expected
    )