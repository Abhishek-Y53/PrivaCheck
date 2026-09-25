import asyncio
from pathlib import Path

from backend.crawler.orchestrator import CrawlerOrchestrator
from backend.rule_engine.loader import RuleLoader
from backend.rule_engine.engine import RuleEngine


async def main():
    url = input("Enter URL: ").strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    rule_file = Path("rules/test/rules.yaml")

    print("\nLoading rules...")
    loader = RuleLoader()
    rules = loader.load(rule_file)

    print(f"Rules loaded: {len(rules)}")

    for rule in rules:
        print(f"  - {rule.id}: {rule.name}")

    print("\nStarting crawler...")

    crawler = CrawlerOrchestrator(
        url=url,
        headless=False,
    )

    crawler_result = await crawler.run()

    print("\n========== CRAWLER ==========")
    print(f"Status       : {crawler_result.status}")
    print(f"Target URL   : {crawler_result.target_url}")
    print(f"Final URL    : {crawler_result.final_url}")
    print(f"Observations : {len(crawler_result.observations)}")

    if crawler_result.error:
        print(f"Error        : {crawler_result.error}")
        return

    print("\nEvaluating rules...")

    engine = RuleEngine()

    results = engine.evaluate_rules(
        rules,
        crawler_result.observations,
    )

    print("\n========== RESULTS ==========")

    for result in results:
        print(f"\nRule       : {result.check_id}")
        print(f"Name       : {result.name}")
        print(f"Status     : {result.status.value}")
        print(f"Severity   : {result.severity.value}")
        print(f"Confidence : {result.confidence:.2f}")
        print(f"Evidence   : {len(result.evidence)}")

        print(f"Explanation: {result.explanation}")

        if result.recommendation:
            print(f"Recommendation: {result.recommendation}")


if __name__ == "__main__":
    asyncio.run(main())