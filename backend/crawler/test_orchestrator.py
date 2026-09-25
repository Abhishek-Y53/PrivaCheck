import asyncio

from backend.crawler.orchestrator import CrawlerOrchestrator


async def main():
    url = input("Enter URL: ").strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    crawler = CrawlerOrchestrator(url, headless=False)

    result = await crawler.run()

    print("\n========== CRAWLER RESULT ==========")
    print(f"Status       : {result.status}")
    print(f"Target URL   : {result.target_url}")
    print(f"Final URL    : {result.final_url}")
    print(f"Observations : {len(result.observations)}")

    if result.error:
        print(f"Error        : {result.error}")

    print("\n--- Sample Observations ---")

    shown = 0

    for observation in result.observations:
        print(f"\nCategory : {observation.category}")
        print(f"Source   : {observation.source_url}")
        print(f"Data     : {observation.data}")

        shown += 1

        if shown == 5:
            break


if __name__ == "__main__":
    asyncio.run(main())