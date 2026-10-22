from pathlib import Path

import pytest

from backend.api.services.scan_pipeline import (
    ScanPipelineService,
    ScanTimeoutError,
    UnsafeScanTargetError,
    UnsupportedFrameworkError,
)
from backend.domain.rules.models import Rule
from backend.schemas.core import CrawlerResult, CrawlerStatus, Observation
from backend.security.url_validation import URLValidationError


def make_rule(evaluator="declarative"):
    return Rule.model_validate(
        {
            "id": "TEST-001",
            "name": "Test rule",
            "description": "Test scan pipeline",
            "category": "TEST",
            "source": {"observation": "dom_button", "match": "any"},
            "evaluator": evaluator,
            "conditions": {
                "all": [
                    {"field": "text", "operator": "contains", "value": "privacy"}
                ]
            },
            "result": {"pass": "PASS", "fail": "FAIL"},
            "severity": "HIGH",
            "recommendation": "Review the test result",
        }
    )


class FakeRuleLoader:
    def __init__(self, rules):
        self.rules = rules
        self.loaded_path = None

    def load(self, path):
        self.loaded_path = path
        return self.rules


class FakeCrawler:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def run(self):
        self.calls += 1
        return self.result


def make_result(status=CrawlerStatus.COMPLETED):
    return CrawlerResult(
        target_url="https://example.com/",
        final_url="https://example.com/",
        observations=[
            Observation(
                category="dom_button",
                source_url="https://example.com/",
                timestamp=1.0,
                data={"text": "privacy settings", "visible": True},
            )
        ],
        started_at=1.0,
        completed_at=2.0,
        status=status,
    )


async def allow_url(url):
    return url


@pytest.mark.asyncio
async def test_scan_pipeline_returns_report_and_uses_registered_rule_file(tmp_path):
    rule_path = tmp_path / "rules.yaml"
    loader = FakeRuleLoader([make_rule()])
    crawler = FakeCrawler(make_result())
    validated_urls = []

    async def validator(url):
        validated_urls.append(url)
        return url

    service = ScanPipelineService(
        crawler_factory=lambda url, headless=True: crawler,
        rule_loader=loader,
        url_validator=validator,
        framework_rule_files={"gdpr": rule_path},
    )

    report = await service.scan("https://example.com/", framework="GDPR")

    assert report.overall_status.value == "PASS"
    assert report.total_checks == 1
    assert report.passed_checks == 1
    assert report.failed_checks == 0
    assert report.metadata["framework"] == "gdpr"
    assert loader.loaded_path == rule_path
    assert validated_urls == ["https://example.com/"]
    assert crawler.calls == 1


@pytest.mark.asyncio
async def test_unknown_framework_is_rejected_without_crawling():
    crawler = FakeCrawler(make_result())
    service = ScanPipelineService(
        crawler_factory=lambda url, headless=True: crawler,
        rule_loader=FakeRuleLoader([make_rule()]),
        url_validator=allow_url,
        framework_rule_files={"gdpr": Path("rules/gdpr/rules.yaml")},
    )

    with pytest.raises(UnsupportedFrameworkError):
        await service.scan("https://example.com/", framework="../../private")

    assert crawler.calls == 0


@pytest.mark.asyncio
async def test_unsafe_dns_result_is_rejected_before_crawler_starts():
    crawler = FakeCrawler(make_result())

    async def blocked_validator(_url):
        raise URLValidationError("private destination")

    service = ScanPipelineService(
        crawler_factory=lambda url, headless=True: crawler,
        rule_loader=FakeRuleLoader([make_rule()]),
        url_validator=blocked_validator,
        framework_rule_files={"gdpr": Path("rules/gdpr/rules.yaml")},
    )

    with pytest.raises(UnsafeScanTargetError):
        await service.scan("https://example.com/", framework="gdpr")

    assert crawler.calls == 0


@pytest.mark.asyncio
async def test_unavailable_evaluator_becomes_manual_review_not_pass():
    crawler = FakeCrawler(make_result())
    service = ScanPipelineService(
        crawler_factory=lambda url, headless=True: crawler,
        rule_loader=FakeRuleLoader([make_rule(evaluator="visual")]),
        url_validator=allow_url,
        framework_rule_files={"gdpr": Path("rules/gdpr/rules.yaml")},
    )

    report = await service.scan("https://example.com/", framework="gdpr")

    assert report.overall_status.value == "MANUAL_REVIEW"
    assert report.issues[0].status.value == "MANUAL_REVIEW"
    assert report.failed_checks == 0


@pytest.mark.asyncio
async def test_state_diff_without_successful_consent_controls_is_manual_review():
    from types import SimpleNamespace

    crawler = FakeCrawler(make_result())
    two_pass_result = SimpleNamespace(
        status=CrawlerStatus.COMPLETED,
        accept=SimpleNamespace(
            status=CrawlerStatus.COMPLETED,
            interaction=SimpleNamespace(status="NOT_FOUND", matched_text=None),
            observations=[],
        ),
        reject=SimpleNamespace(
            status=CrawlerStatus.COMPLETED,
            interaction=SimpleNamespace(status="NOT_FOUND", matched_text=None),
            observations=[],
        ),
        accept_observations=[],
        reject_observations=[],
    )

    async def fake_two_pass(_url):
        return two_pass_result

    service = ScanPipelineService(
        crawler_factory=lambda url, headless=True: crawler,
        rule_loader=FakeRuleLoader([make_rule(evaluator="state_diff")]),
        url_validator=allow_url,
        framework_rule_files={"gdpr": Path("rules/gdpr/rules.yaml")},
        two_pass_scan=fake_two_pass,
    )

    report = await service.scan("https://example.com/", framework="gdpr")

    assert report.overall_status.value == "MANUAL_REVIEW"
    assert report.issues[0].status.value == "MANUAL_REVIEW"
    assert report.metadata["two_pass"]["available"] is True
    assert report.metadata["two_pass"]["accept"]["interaction_status"] == "NOT_FOUND"
    assert report.metadata["two_pass"]["reject"]["interaction_status"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_scan_wall_clock_timeout_is_controlled():
    class SlowCrawler:
        async def run(self):
            import asyncio
            await asyncio.sleep(1)
            return make_result()

    service = ScanPipelineService(
        crawler_factory=lambda url, headless=True: SlowCrawler(),
        rule_loader=FakeRuleLoader([make_rule()]),
        url_validator=allow_url,
        framework_rule_files={"gdpr": Path("rules/gdpr/rules.yaml")},
        scan_timeout_seconds=0.01,
    )

    with pytest.raises(ScanTimeoutError):
        await service.scan("https://example.com/", framework="gdpr")


@pytest.mark.asyncio
async def test_unsupported_scheme_is_rejected_before_dns_or_crawl():
    crawler = FakeCrawler(make_result())
    service = ScanPipelineService(
        crawler_factory=lambda url, headless=True: crawler,
        rule_loader=FakeRuleLoader([make_rule()]),
        url_validator=lambda _url: pytest.fail("DNS validator should not run"),
        framework_rule_files={"gdpr": Path("rules/gdpr/rules.yaml")},
    )

    with pytest.raises(UnsafeScanTargetError):
        await service.scan("file:///etc/passwd", framework="gdpr")

    assert crawler.calls == 0
