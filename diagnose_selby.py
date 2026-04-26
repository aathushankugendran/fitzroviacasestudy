"""
Run this to inspect the Selby page live.
Usage: python diagnose_selby.py
"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        api_calls = []

        async def on_response(r):
            if r.status == 200:
                try:
                    ct = r.headers.get("content-type","")
                    if "json" in ct:
                        data = await r.json()
                        size = len(str(data))
                        if size > 100:
                            api_calls.append({"url": r.url, "size": size, "type": type(data).__name__})
                except Exception:
                    pass

        page.on("response", on_response)

        url = "https://triconliving.com/apartment/the-selby/#your-perfect-layout"
        print(f"Loading {url} ...")
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(4000)

        print(f"\n=== JSON API calls ({len(api_calls)}) ===")
        for c in api_calls:
            print(f"  {c['url'][:100]}")
            print(f"    type={c['type']}, size={c['size']}")

        print("\n=== Buttons/tabs visible ===")
        buttons = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, [role="tab"], a'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    tag: el.tagName,
                    text: (el.innerText || '').trim().slice(0,50),
                    cls: el.className.slice(0,60)
                }))
                .filter(b => b.text)
                .slice(0, 40)
        """)
        for b in buttons:
            print(f"  <{b['tag']}> '{b['text']}' class='{b['cls']}'")

        print("\n=== Tables on page ===")
        tables = await page.evaluate("""
            () => Array.from(document.querySelectorAll('table')).map(t => ({
                rows: t.querySelectorAll('tr').length,
                preview: t.innerText.slice(0, 200)
            }))
        """)
        for i, t in enumerate(tables):
            print(f"  Table {i}: {t['rows']} rows")
            print(f"    Preview: {t['preview'][:100]}")

        print("\n=== Elements containing '$' and unit numbers ===")
        units = await page.evaluate("""
            () => {
                const results = [];
                const all = document.querySelectorAll('tr, [class*="row"], [class*="unit"], [class*="listing"]');
                for (const el of all) {
                    const txt = (el.innerText || '').trim();
                    if (txt.includes('$') && txt.match(/#\d{3,4}|\d{4}/)) {
                        results.push(txt.slice(0, 100));
                    }
                }
                return results.slice(0, 10);
            }
        """)
        for u in units:
            print(f"  {u}")

        await browser.close()

asyncio.run(main())
