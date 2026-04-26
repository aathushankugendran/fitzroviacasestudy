"""
Diagnose Story of Midtown API — prints exact field names and values.
Run this to see what the rentsync API returns.

Usage: python diagnose_story.py
"""
import asyncio
from loguru import logger
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        captured = []

        async def on_response(response):
            if response.status == 200:
                try:
                    ct = response.headers.get("content-type","")
                    if "json" in ct:
                        url = response.url
                        data = await response.json()
                        items = data if isinstance(data, list) else next(
                            (data[k] for k in ("data","units","suites","results") if k in data and isinstance(data[k],list)),
                            None
                        )
                        if items and len(items) > 0:
                            captured.append({"url": url, "items": items})
                except Exception:
                    pass

        page.on("response", on_response)
        print("Loading mystorymidtown.com/suites ...")
        await page.goto("https://www.mystorymidtown.com/suites", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(4000)
        await browser.close()

    print(f"\nCaptured {len(captured)} JSON responses\n")
    for cap in captured:
        items = cap["items"]
        print(f"URL: {cap['url']}")
        print(f"Items: {len(items)}")
        if items:
            first = items[0]
            print(f"KEYS: {list(first.keys())}")
            print(f"FIRST ITEM VALUES:")
            for k, v in first.items():
                print(f"  {k!r}: {v!r}")
        print("---")

asyncio.run(main())
