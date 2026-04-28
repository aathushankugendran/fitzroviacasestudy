"""
The Montgomery — 2388 Yonge Street
Playwright only — Cloudflare requires real browser on Railway.

Confirmed working in Railway logs (Apr 28):
  [Montgomery] Playwright oriole: 2 unit(s)
The approach works — Cloudflare DOES clear. The fix is waiting
properly and using fetch() after it clears (not page.goto per page).
"""

import re
from bs4 import BeautifulSoup
from loguru import logger
from scraper.base import BaseScraper, UnitData

FLOORPLANS_URL = "https://www.themontgomery.ca/floorplans"


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
        units = []
        seen = set()

        try:
            # Navigate to /floorplans and wait for Cloudflare to clear
            logger.info("[The Montgomery] Navigating — waiting for Cloudflare...")
            await page.goto(FLOORPLANS_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)

            for i in range(30):
                title = await page.title()
                if not any(x in title.lower() for x in ["moment", "verify", "security", "checking"]):
                    logger.info(f"[The Montgomery] Cloudflare cleared at {i}s: {title}")
                    break
                logger.info(f"[The Montgomery] Waiting for Cloudflare {i}s: {title}")
                await page.wait_for_timeout(1000)
            else:
                logger.error("[The Montgomery] Cloudflare did not clear — aborting")
                return []

            await page.wait_for_timeout(2000)

            # Fetch all 8 floor plans in parallel using Cloudflare cookies
            logger.info("[The Montgomery] Fetching all floor plans in parallel...")
            raw = await page.evaluate("""
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
                            const r = await fetch(url, {
                                credentials: 'include',
                                headers: {
                                    'Referer': 'https://www.themontgomery.ca/floorplans',
                                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                                }
                            });
                            const html = await r.text();
                            const doc = new DOMParser().parseFromString(html, 'text/html');
                            const name = doc.querySelector('h1')?.textContent?.trim() || '';
                            const body = doc.body?.textContent || '';
                            const beds = body.match(/(\\d+)\\s*Bedroom/i)?.[1];
                            const bath = body.match(/(\\d+(?:\\.\\d)?)\\s*Bathroom/i)?.[1];
                            const sqft = (body.match(/Up to ([\\d,]+)\\s*Sq/i) || body.match(/([\\d,]+)\\s*Sq\\.\\s*Ft/i))?.[1];
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
                            return {url, name, beds, bath, sqft, cards, status: r.status};
                        } catch(e) {
                            return {url, cards: [], error: e.message};
                        }
                    }));
                }
            """)

            logger.info(f"[The Montgomery] Parallel fetch done: {len(raw)} pages")
            for pd in raw:
                fp_name  = pd.get("name") or pd["url"].split("/")[-1]
                beds_raw = pd.get("beds")
                bath_raw = pd.get("bath")
                sqft_raw = (pd.get("sqft") or "").replace(",","")
                fp_url   = pd["url"]
                if pd.get("error"):
                    logger.warning(f"[The Montgomery] {fp_name}: {pd['error']}")
                    continue

                beds      = int(beds_raw) if beds_raw else -1
                bathrooms = float(bath_raw) if bath_raw else None
                sqft      = int(sqft_raw) if sqft_raw.isdigit() else None
                unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")
                logger.info(f"[The Montgomery] {fp_name}: {len(pd.get('cards',[]))} cards | HTTP {pd.get('status')}")

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
                    avail_str = "Available Now"
                    if card.get("date"):
                        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", card["date"])
                        if m:
                            try:
                                from datetime import datetime
                                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                                avail_str = dt.strftime("%b {}, %Y").format(dt.day)
                            except Exception:
                                avail_str = card["date"]
                    units.append(UnitData(
                        unit_number=unit_num, unit_type=unit_type,
                        bedrooms=beds, bathrooms=bathrooms,
                        floor_plan_name=fp_name, sq_ft=sqft,
                        monthly_rent=rent, available_date=avail_str,
                        incentives=None, source_url=fp_url,
                    ))
                    logger.debug(f"[The Montgomery] ✓ #{unit_num} | {fp_name} | {unit_type} | ${rent}")

        except Exception as e:
            logger.error(f"[The Montgomery] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Montgomery] Total: {len(units)} apartments")
        return units
