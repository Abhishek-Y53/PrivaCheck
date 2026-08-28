import asyncio

from backend.crawler.browser import BrowserManager
from backend.crawler.network import NetworkCollector


async def main():
    url = input("Enter URL: ").strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    manager = BrowserManager(headless=False)

    await manager.start()

    context, page = await manager.create_context_and_page()

    network_collector = NetworkCollector(page, url)
    network_collector.start_collecting()

    try:
        print(f"\nOpening: {url}\n")

        response = await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        print(f"Final URL: {page.url}")

        if response:
            print(f"Main Response Status: {response.status}")

        observations = network_collector.get_observations()

        print(f"\nTotal Network Observations: {len(observations)}")

        print("\n--- Sample Network Observations ---")

        for observation in observations[:15]:
            print(f"\nCategory : {observation.category}")
            print(f"Time     : {observation.timestamp}")
            print(f"Source   : {observation.source_url}")
            print(f"Data     : {observation.data}")

    except Exception as e:
        print(f"\nError while scanning: {e}")

    finally:
        network_collector.stop_collecting()
        await page.close()
        await context.close()
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())