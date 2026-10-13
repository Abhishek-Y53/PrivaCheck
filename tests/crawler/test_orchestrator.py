import asyncio

from backend.crawler.orchestrator import CrawlerOrchestrator

import pytest

@pytest.mark.asyncio
async def test_orchestrator_returns_page_context_observation():
    orchestrator = CrawlerOrchestrator(
        "https://example.com"
    )

    result = await orchestrator.run()

    assert result.status == "COMPLETED"

    page_context_observations = [
        observation
        for observation in result.observations
        if observation.category == "page_context"
    ]

    assert len(page_context_observations) == 1

    page_context = page_context_observations[0]

    assert page_context.data["final_url"] == result.final_url
    assert page_context.data["protocol"] == "https"
    assert page_context.data["is_https"] is True

    assert isinstance(
        page_context.data["has_forms"],
        bool,
    )

    assert isinstance(
        page_context.data["form_count"],
        int,
    )
