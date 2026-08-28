import asyncio

from backend.crawler.browser import BrowserManager
from backend.crawler.dom import DOMCollector
from backend.crawler.links import LinkCollector
from backend.crawler.storage import StorageCollector


async def main():
    url = input("Enter URL: ").strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    manager = BrowserManager(headless=False)

    await manager.start()

    context, page = await manager.create_context_and_page()

    try:
        print(f"\nOpening: {url}\n")

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # -------------------------
        # DOM
        # -------------------------
        dom_collector = DOMCollector(page, url)
        dom_observations = await dom_collector.collect_all()

        # -------------------------
        # LINKS
        # -------------------------
        link_collector = LinkCollector(page, url)
        link_observations = await link_collector.collect_links()

        # -------------------------
        # STORAGE
        # -------------------------
        storage_collector = StorageCollector(page, url)
        storage_observations = await storage_collector.collect_all()

        # -------------------------
        # DISPLAY ONE OBSERVATION
        # -------------------------

        print("========== DOM ==========")

        if dom_observations:
            observation = dom_observations[0]

            print(f"Category : {observation.category}")
            print(f"Source   : {observation.source_url}")
            print(f"Data     : {observation.data}")
        else:
            print("No DOM observations found.")

        print("\n========== LINKS ==========")

        if link_observations:
            #observation = link_observations[0]
            for observation in link_observations[:10]:
                print(f"Category : {observation.category}")
                print(f"Source   : {observation.source_url}")
                print(f"Data     : {observation.data}")
        else:
            print("No link observations found.")

        print("\n========== STORAGE ==========")

        if storage_observations:
            observation = storage_observations[0]

            print(f"Category : {observation.category}")
            print(f"Source   : {observation.source_url}")
            print(f"Data     : {observation.data}")
        else:
            print("No storage observations found.")

    except Exception as e:
        print(f"\nError while scanning: {e}")

    finally:
        await page.close()
        await context.close()
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())