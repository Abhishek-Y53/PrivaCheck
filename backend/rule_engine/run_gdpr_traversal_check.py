
import asyncio
from collections import Counter
from pathlib import Path

from backend.crawler.orchestrator import CrawlerOrchestrator
from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.loader import RuleLoader


GDPR_RULE_IDS = {
    "GDPR-006",
    "GDPR-008",
    "GDPR-009",
    "GDPR-010",
}


async def main():
    website = input("Enter website URL: ").strip()

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    rule_file = Path("rules/gdpr/rules.yaml")

    print("\n========== LOADING GDPR RULES ==========")

    loader = RuleLoader()
    all_rules = loader.load(rule_file)

    selected_rules = [
        rule
        for rule in all_rules
        if rule.id in GDPR_RULE_IDS
    ]

    found_ids = {rule.id for rule in selected_rules}
    missing_ids = GDPR_RULE_IDS - found_ids

    if missing_ids:
        print("Missing expected rules:", sorted(missing_ids))
        return

    selected_rules = [
        rule
        for rule in selected_rules
        if rule.evaluator == "declarative"
    ]

    print(f"GDPR rules loaded: {len(all_rules)}")

    for rule in selected_rules:
        print(f"  {rule.id}: {rule.name}")

    print("\n========== RUNNING CRAWLER ==========")

    crawler = CrawlerOrchestrator(
        url=website,
        headless=True,
    )

    crawler_result = await crawler.run()

    print("Status:", crawler_result.status)
    print("Final URL:", crawler_result.final_url)
    print("Error:", crawler_result.error)

    if crawler_result.status.value != "COMPLETED":
        print("Crawler failed; rule evaluation skipped.")
        return

    observations = crawler_result.observations

    print("Total observations:", len(observations))

    links = [
        observation
        for observation in observations
        if observation.category == "link"
    ]

    print("\n========== CRAWL COVERAGE ==========")

    print("Link observations:", len(links))

    print(
        "Links by depth:",
        Counter(
            observation.data.get("crawl_depth", "MISSING")
            for observation in links
        ),
    )

    text_observations = [
        observation
        for observation in observations
        if observation.category == "dom_visible_text"
    ]

    visited_text_urls = sorted({
        observation.source_url
        for observation in text_observations
    })

    print("Pages with visible text:", len(visited_text_urls))

    for url in visited_text_urls:
        print(" ", url)

    # ---------------------------------------------------------
    # Diagnostic: inspect candidate evidence for data rights
    # ---------------------------------------------------------

    link_terms = (
        "access",
        "request",
        "export",
        "download",
        "delete",
        "erase",
        "rectif",
        "portability",
        "dsar",
        "account",
        "privacy",
    )

    print("\n========== CANDIDATE LINKS ==========")

    candidate_count = 0

    for observation in links:
        data = observation.data

        text = data.get("text", "")
        href = data.get("href", "")

        if not isinstance(text, str):
            text = ""

        if not isinstance(href, str):
            href = ""

        searchable = f"{text} {href}".casefold()

        if any(term in searchable for term in link_terms):
            print(
                f"[depth={data.get('crawl_depth', 'MISSING')}] "
                f"[region={data.get('region', 'unknown')}] "
                f"{text!r} -> {href}"
            )

            candidate_count += 1

            if candidate_count >= 60:
                print("Output limited to the first 60 matching links.")
                break

    text_terms = (
        "access",
        "request",
        "export",
        "download",
        "delete",
        "erase",
        "rectification",
        "portability",
        "exercise your rights",
        "personal data",
    )

    print("\n========== RELEVANT PAGE TEXT ==========")

    for observation in text_observations:
        page_text = observation.data.get("text", "")

        if not isinstance(page_text, str):
            continue

        normalized_text = page_text.casefold()
        snippets = []

        for term in text_terms:
            position = normalized_text.find(term)

            if position < 0:
                continue

            start = max(0, position - 120)
            end = min(len(page_text), position + 280)

            snippet = " ".join(
                page_text[start:end].split()
            )

            if snippet not in snippets:
                snippets.append(snippet)

        if snippets:
            print(f"\nPage: {observation.source_url}")

            for snippet in snippets[:5]:
                print(" ", snippet)

    print("\n========== EVALUATING GDPR RULES ==========")

    engine = RuleEngine()

    results = engine.evaluate_rules(
        selected_rules,
        observations,
    )

    for result in results:
        print(f"\nRule: {result.check_id}")
        print(f"Name: {result.name}")
        print(f"Status: {result.status.value}")
        print(f"Confidence: {result.confidence:.2f}")
        print(f"Evidence count: {len(result.evidence)}")
        print(f"Explanation: {result.explanation}")

        if result.recommendation:
            print(f"Recommendation: {result.recommendation}")

        if result.evidence:
            print("Evidence details:")

            for evidence in result.evidence[:5]:
                print(" ", evidence)

    print("\n========== DIAGNOSTIC COMPLETE ==========")


if __name__ == "__main__":
    asyncio.run(main())
