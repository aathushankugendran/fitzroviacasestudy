"""
The Montgomery — 2388 Yonge Street

WORKING APPROACH (confirmed in Chrome Apr 28 2026):
- Navigate to /floorplans once with Playwright → passes Cloudflare
- Then use page.evaluate(Promise.all(fetch())) with credentials:'include'
- Each fetch uses the Cloudflare cookies set by the initial navigation
- Status 200, data returned in ~1s per page, all 8 pages in parallel

This is identical to how it worked when it scraped Oriole successfully.
The fix is waiting properly for Cloudflare before fetching.

CRITICAL regex: "$2,812 /Month" — space before /Month, needs \\s*
"""

import re
from bs4 import BeautifulSoup
from loguru import logger
from scraper.base import BaseScraper, UnitData

FLOORPLANS_URL = "https://www.themontgomery.ca/floorplans"

FP_URLS = [
    "https://www.themontgomery.ca/floorplans/oriole",
    "https://www.themontgomery.ca/floorplans/lillian---d",
    "https://www.themontgomery.ca/floorplans/roselawn-iii---penthouse-collection",
    "https://www.themontgomery.ca/floorplans/anderson---d",
    "https://www.themontgomery.ca/floorplans/maxwell",
    "https://www.themontgomery.ca/floorplans/broadway-ii---th",
    "https://www.themontgomery.ca/floorplans/redpath-iv",
    "https://www.themontgomery.ca/floorplans/oswald",
]


class MontgomeryScraper(BaseScraper):
    building_name = "The Montgomery"
    building_address = "2388 Yonge Street, Toronto, ON"
    url = FLOORPLANS_URL

    async def _start_browser(self, playwright):
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-CA",
        )
        await self._context.add_init_script("""
            delete Object.getPrototypeOf(navigator).webdriver;
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        """)

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(30_000)
        units = []
        seen = set()

        try:
            # Step 1: Navigate to /floorplans and wait for Cloudflare to clear
            logger.info("[The Montgomery] Navigating to /floorplans...")
            await page.goto(FLOORPLANS_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)

            # Wait up to 30s for Cloudflare to clear
            for i in range(30):
                title = await page.title()
                if not any(x in title.lower() for x in ["moment", "verify", "security", "checking"]):
                    logger.info(f"[The Montgomery] Ready after {i}s: {title}")
                    break
                logger.info(f"[The Montgomery] Cloudflare... {i}s: {title}")
                await page.wait_for_timeout(1000)
            else:
                logger.error("[The Montgomery] Cloudflare did not clear in 30s")
                return []

            await page.wait_for_timeout(1000)

            # Step 2: Fetch all 8 floor plan pages in PARALLEL using browser cookies
            # Confirmed working: status 200, data in ~1s, no new Cloudflare challenge
            logger.info("[The Montgomery] Fetching all 8 floor plans in parallel...")
            raw_results = await page.evaluate("""
                async () => {
                    const urls = [
                        'https://www.themontgomery.ca/floorplans/oriole',
                        'https://www.themontgomery.ca/floorplans/lillian---d',
                        'https://www.themontgomery.ca/floorplans/roselawn-iii---penthouse-collection',
                        'https://www.themontgomery.ca/floorplans/anderson---d',
                        'https://www.themontgomery.ca/floorplans/maxwell',
                        'https://www.themontgomery.ca/floorplans/broadway-ii---th',
                        'https://www.themontgomery.ca/floorplans/redpath-iv',
                        'https://www.themontgomery.ca/floorplans/oswald'
                    ];

                    return await Promise.all(urls.map(async url => {
                        try {
                            const r = await fetch(url, {credentials: 'include'});
                            const html = await r.text();
                            const doc = new DOMParser().parseFromString(html, 'text/html');

                            const name = doc.querySelector('h1')?.textContent?.trim() || '';
                            const body = doc.body?.textContent || '';
                            const beds = body.match(/(\\d+)\\s*Bedroom/i)?.[1];
                            const bath = body.match(/(\\d+(?:\\.\\d)?)\\s*Bathroom/i)?.[1];
                            const sqftM = body.match(/Up to ([\\d,]+)\\s*Sq/i) ||
                                          body.match(/([\\d,]+)\\s*Sq\\.\\s*Ft/i);

                            const cards = Array.from(doc.querySelectorAll('div[class*="card-body"]'))
                                .filter(c => c.textContent.includes('Apartment:'))
                                .map(c => {
                                    const t = c.textContent.replace(/\\s+/g, ' ').trim();
                                    return {
                                        apt:  t.match(/Apartment:\\s*#\\s*(\\w+)/i)?.[1],
                                        date: t.match(/Date Available:\\s*([\\d/]+)/i)?.[1],
                                        rent: t.match(/Starting at:\\s*\\$([\\d,]+)\\s*\\/Month/i)?.[1]
                                    };
                                }).filter(c => c.apt && c.rent);

                            return {url, name, beds, bath, sqft: sqftM?.[1], cards, status: r.status};
                        } catch(e) {
                            return {url, cards: [], error: e.message, status: 0};
                        }
                    }));
                }
            """)

            logger.info(f"[The Montgomery] Got results for {len(raw_results)} pages")

            # Step 3: Parse results
            for pd in raw_results:
                fp_name  = pd.get("name") or pd["url"].split("/")[-1]
                beds_raw = pd.get("beds")
                bath_raw = pd.get("bath")
                sqft_raw = (pd.get("sqft") or "").replace(",","")
                fp_url   = pd["url"]
                status   = pd.get("status", 0)

                if pd.get("error"):
                    logger.warning(f"[The Montgomery] {fp_name}: error — {pd['error']}")
                    continue

                beds      = int(beds_raw) if beds_raw else -1
                bathrooms = float(bath_raw) if bath_raw else None
                sqft      = int(sqft_raw) if sqft_raw.isdigit() else None
                unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")

                logger.info(f"[The Montgomery] {fp_name}: {len(pd.get('cards',[]))} cards | HTTP {status}")

                for card in pd.get("cards", []):
                    unit_num = (card.get("apt") or "").strip()
                    if not unit_num or unit_num in seen:
                        continue
                    seen.add(unit_num)

                    try:
                        rent = float(card["rent"].replace(",",""))
                    except Exception:
                        continue
                    if rent < 500:
                        continue

                    avail_raw = card.get("date")
                    avail_str = "Available Now"
                    if avail_raw:
                        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", avail_raw)
                        if m:
                            try:
                                from datetime import datetime
                                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                                avail_str = dt.strftime("%b {}, %Y").format(dt.day)
                            except Exception:
                                avail_str = avail_raw

                    units.append(UnitData(
                        unit_number=unit_num,
                        unit_type=unit_type,
                        bedrooms=beds,
                        bathrooms=bathrooms,
                        floor_plan_name=fp_name,
                        sq_ft=sqft,
                        monthly_rent=rent,
                        available_date=avail_str,
                        incentives=None,
                        source_url=fp_url,
                    ))
                    logger.debug(f"[The Montgomery] ✓ #{unit_num} | {fp_name} | {unit_type} | ${rent}")

        except Exception as e:
            logger.error(f"[The Montgomery] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Montgomery] Total: {len(units)} apartments")
        return units
