import pytest

from backend.crawler import (
    two_pass as two_pass_module,
)
from backend.crawler.pass_runner import (
    SinglePassResult,
)
from backend.crawler.two_pass import (
    ConsentInteractionResult,
    TwoPassRunner,
)
from backend.schemas.core import (
    CrawlerStatus,
    Observation,
)


class FakePage:

    def __init__(self, context_id: int):
        self.context_id = context_id
        self.url = "https://www.iiitg.ac.in/"

    async def close(self):
        pass


class FakeContext:

    def __init__(
        self,
        browser,
        context_id: int,
    ):
        self.browser = browser
        self.context_id = context_id
        self.closed = False

    async def new_page(self):
        return FakePage(
            self.context_id
        )

    async def close(self):
        self.closed = True


class FakeBrowser:

    def __init__(self):
        self.next_id = 1
        self.created_context_ids = []

    async def new_context(self):

        context_id = self.next_id

        self.next_id += 1

        self.created_context_ids.append(
            context_id
        )

        return FakeContext(
            self,
            context_id,
        )


class FakeSinglePassRunner:

    calls = []

    def __init__(
        self,
        page,
        context,
        url,
        *,
        wait_ms,
        post_action_wait_ms,
    ):

        self.page = page
        self.context = context
        self.url = url

    async def run(
        self,
        post_navigation_action=None,
    ):

        interaction = (
            await post_navigation_action(
                self.page
            )
        )

        FakeSinglePassRunner.calls.append(
            (
                self.context.context_id,
                interaction.action,
            )
        )

        observation = Observation(
            category="test_snapshot",
            source_url=self.url,
            timestamp=1.0,
            data={
                "context_id":
                    self.context.context_id
            },
        )

        return SinglePassResult(
            target_url=self.url,
            final_url=self.url + "/",
            observations=[observation],
            started_at=1.0,
            completed_at=2.0,
            status=CrawlerStatus.COMPLETED,
            action_result=interaction,
        )


@pytest.mark.asyncio
async def test_two_pass_uses_fresh_context_for_each_pass(
    monkeypatch,
):

    FakeSinglePassRunner.calls = []

    monkeypatch.setattr(
        two_pass_module,
        "SinglePassRunner",
        FakeSinglePassRunner,
    )

    async def fake_interact(
        page,
        action,
    ):
        return ConsentInteractionResult(
            action=action,
            status="SUCCESS",
        )

    browser = FakeBrowser()

    base_context = FakeContext(
        browser,
        0,
    )

    base_page = FakePage(0)

    runner = TwoPassRunner(
        base_page,
        base_context,
        "https://www.iiitg.ac.in/",
        wait_ms=0,
        consent_wait_ms=0,
    )

    runner._interact_with_consent = (
        fake_interact
    )

    result = await runner.run()

    assert (
        result.status
        == CrawlerStatus.COMPLETED
    )

    assert browser.created_context_ids == [
        1,
        2,
    ]

    assert (
        result.accept.interaction.status
        == "SUCCESS"
    )

    assert (
        result.reject.interaction.status
        == "SUCCESS"
    )

    assert (
        result.accept_observations[0]
        .data["context_id"]
        !=
        result.reject_observations[0]
        .data["context_id"]
    )


@pytest.mark.asyncio
async def test_missing_consent_control_is_not_a_crawler_failure(
    monkeypatch,
):

    monkeypatch.setattr(
        two_pass_module,
        "SinglePassRunner",
        FakeSinglePassRunner,
    )

    async def fake_interact(
        page,
        action,
    ):

        return ConsentInteractionResult(
            action=action,
            status="NOT_FOUND",
            error=(
                f"No {action} control"
            ),
        )

    browser = FakeBrowser()

    base_context = FakeContext(
        browser,
        0,
    )

    base_page = FakePage(0)

    runner = TwoPassRunner(
        base_page,
        base_context,
        "https://www.iiitg.ac.in/",
        wait_ms=0,
        consent_wait_ms=0,
    )

    runner._interact_with_consent = (
        fake_interact
    )

    result = await runner.run()

    assert (
        result.status
        == CrawlerStatus.COMPLETED
    )

    assert result.error is None

    assert (
        result.accept.interaction.status
        == "NOT_FOUND"
    )

    assert (
        result.reject.interaction.status
        == "NOT_FOUND"
    )

    assert len(
        result.accept_observations
    ) == 1

    assert len(
        result.reject_observations
    ) == 1