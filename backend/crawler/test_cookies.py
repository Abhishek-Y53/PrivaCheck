import asyncio

from backend.crawler.browser import BrowserManager
from backend.crawler.cookies import CookieCollector


async def main():
    url = input("Enter URL: ").strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    manager = BrowserManager(headless=False)

    await manager.start()

    context, page = await manager.create_context_and_page()

    collector = CookieCollector(context, url)

    try:
        print(f"\nOpening: {url}\n")

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        observations = await collector.collect()

        print(f"Total Cookies Found: {len(observations)}")

        print("\n--- Cookie Observations ---")

        for observation in observations:
            cookie = observation.data

            print("\nCookie")
            print(f"  Name     : {cookie.get('name')}")
            print(f"  Domain   : {cookie.get('domain')}")
            print(f"  Path     : {cookie.get('path')}")
            print(f"  Secure   : {cookie.get('secure')}")
            print(f"  HttpOnly : {cookie.get('httpOnly')}")
            print(f"  SameSite : {cookie.get('sameSite')}")
            print(f"  Expires  : {cookie.get('expires')}")

    except Exception as e:
        print(f"\nError while scanning: {e}")

    finally:
        await page.close()
        await context.close()
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())