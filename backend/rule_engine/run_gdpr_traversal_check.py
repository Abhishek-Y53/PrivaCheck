import asyncio
from collections import Counter
from pathlib import Path

from backend.crawler.orchestrator import CrawlerOrchestrator
from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.loader import RuleLoader


async def main():
    website = input("Enter website URL: ").strip()

    if not website:
        print("Error: Website URL cannot be empty.")
        return

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    rule_file = Path("rules/gdpr/rules.yaml")

    # ---------------------------------------------------------
    # 1. Load all declarative rules from the selected YAML file
    # ---------------------------------------------------------

    print("\n========== LOADING RULES ==========")

    loader = RuleLoader()
    all_rules = loader.load(rule_file)

    selected_rules = [
        rule
        for rule in all_rules
        if rule.evaluator == "declarative"
    ]

    print(f"Rules loaded: {len(all_rules)}")
    print(
        "Declarative rules evaluated:",
        len(selected_rules),
    )

    for rule in selected_rules:
        print(f"  {rule.id}: {rule.name}")

    if not selected_rules:
        print("No declarative rules found. Nothing to evaluate.")
        return

    # ---------------------------------------------------------
    # 2. Run the crawler
    # ---------------------------------------------------------

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
        print("Crawler failed. Rule evaluation skipped.")
        return

    observations = crawler_result.observations

    print("Total observations:", len(observations))

    # ---------------------------------------------------------
    # 3. Inspect crawl coverage
    # ---------------------------------------------------------

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

    visited_text_urls = sorted(
        {
            observation.source_url
            for observation in text_observations
        }
    )

    print("Pages with visible text:", len(visited_text_urls))

    for url in visited_text_urls:
        print(" ", url)

    # ---------------------------------------------------------
    # 4. Inspect candidate links
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

        text_value = data.get("text", "")
        href = data.get("href", "")

        if not isinstance(text_value, str):
            text_value = ""

        if not isinstance(href, str):
            href = ""

        searchable = f"{text_value} {href}".casefold()

        if any(term in searchable for term in link_terms):
            print(
                f"[depth={data.get('crawl_depth', 'MISSING')}] "
                f"[region={data.get('region', 'unknown')}] "
                f"{text_value!r} -> {href}"
            )

            context_text = data.get("context_text", "")

            if isinstance(context_text, str) and context_text:
                print(f"    Context: {context_text[:300]}")

            candidate_count += 1

            if candidate_count >= 60:
                print(
                    "Output limited to the first 60 matching links."
                )
                break

    # ---------------------------------------------------------
    # 5. Inspect relevant visible page text
    # ---------------------------------------------------------

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
        "data protection officer",
        "supervisory authority",
        "withdraw consent",
        "retention period",
        "automated decision",
        "data breach",
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

    # ---------------------------------------------------------
    # 6. Evaluate all declarative rules
    # ---------------------------------------------------------

    print("\n========== EVALUATING RULES ==========")

    engine = RuleEngine()

    results = engine.evaluate_rules(
        selected_rules,
        observations,
    )

    # ---------------------------------------------------------
    # 7. Display results and supporting evidence
    # ---------------------------------------------------------

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
            print(
                f"Recommendation: {result.recommendation}"
            )

        if result.evidence:
            print("Evidence details:")

            for evidence in result.evidence[:5]:
                print(" ", evidence)

            if len(result.evidence) > 5:
                print(
                    f"  ... and {len(result.evidence) - 5} "
                    "additional evidence observation(s)"
                )

    # ---------------------------------------------------------
    # 8. Summary
    # ---------------------------------------------------------

    status_counts = Counter(
        result.status.value for result in results
    )

    print("\n========== SUMMARY ==========")
    print("Rules evaluated:", len(results))

    for status, count in sorted(status_counts.items()):
        print(f"{status}: {count}")

    print("\n========== DIAGNOSTIC COMPLETE ==========")


if __name__ == "__main__":
    asyncio.run(main())