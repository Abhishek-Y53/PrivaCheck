import pytest

from backend.crawler.orchestrator import CrawlerOrchestrator
from backend.schemas.core import CrawlerStatus


@pytest.mark.asyncio
async def test_real_https_site_produces_tls_observation():
    orchestrator = CrawlerOrchestrator(
        "https://example.com",
        headless=True,
    )

    result = await orchestrator.run()

    assert result.status == CrawlerStatus.COMPLETED

    tls_observations = [
        observation
        for observation in result.observations
        if observation.category == "tls_certificate"
    ]

    assert len(tls_observations) == 1

    tls = tls_observations[0]

    assert tls.data["protocol"] == "https"
    assert tls.data["verified"] is True
    assert tls.data["hostname"] == "example.com"
    assert tls.data["error"] is None