from backend.schemas.core import Observation
from backend.crawler.orchestrator import CrawlerOrchestrator


def test_page_context_for_https_page_with_forms():
    orchestrator = CrawlerOrchestrator(
        "https://example.com"
    )

    dom_observations = [
        Observation(
            category="dom_form",
            source_url="https://example.com",
            timestamp=1.0,
            data={
                "action": "https://example.com/login",
                "method": "post",
            },
        ),
        Observation(
            category="dom_form",
            source_url="https://example.com",
            timestamp=2.0,
            data={
                "action": "https://example.com/contact",
                "method": "post",
            },
        ),
    ]

    context_observation = (
        orchestrator._build_page_context_observation(
            "https://example.com",
            dom_observations,
        )
    )

    assert context_observation.category == "page_context"

    assert (
        context_observation.data["protocol"]
        == "https"
    )

    assert (
        context_observation.data["is_https"]
        is True
    )

    assert (
        context_observation.data["has_forms"]
        is True
    )

    assert (
        context_observation.data["form_count"]
        == 2
    )


def test_page_context_for_https_page_without_forms():
    orchestrator = CrawlerOrchestrator(
        "https://example.com"
    )

    dom_observations = []

    context_observation = (
        orchestrator._build_page_context_observation(
            "https://example.com",
            dom_observations,
        )
    )

    assert context_observation.category == "page_context"

    assert (
        context_observation.data["protocol"]
        == "https"
    )

    assert (
        context_observation.data["is_https"]
        is True
    )

    assert (
        context_observation.data["has_forms"]
        is False
    )

    assert (
        context_observation.data["form_count"]
        == 0
    )


def test_page_context_for_http_page_with_forms():
    orchestrator = CrawlerOrchestrator(
        "http://example.com"
    )

    dom_observations = [
        Observation(
            category="dom_form",
            source_url="http://example.com",
            timestamp=1.0,
            data={
                "action": "http://example.com/login",
                "method": "post",
            },
        ),
    ]

    context_observation = (
        orchestrator._build_page_context_observation(
            "http://example.com",
            dom_observations,
        )
    )

    assert context_observation.category == "page_context"

    assert (
        context_observation.data["protocol"]
        == "http"
    )

    assert (
        context_observation.data["is_https"]
        is False
    )

    assert (
        context_observation.data["has_forms"]
        is True
    )

    assert (
        context_observation.data["form_count"]
        == 1
    )