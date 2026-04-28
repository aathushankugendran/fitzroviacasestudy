"""
The Montgomery — 2388 Yonge Street
Strategy: httpx first, Playwright fallback.
On Railway: httpx gets 403, Playwright fallback used.
Cloudflare shows "Just a moment..." — must wait for it to clear before scraping.
"""

import re
import httpx
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://www.themontgomery.ca/floorplans",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


class MontgomeryScraper(BaseScraper):
    building_name = "The Montgomery"
    building_address = "2388 Yonge Street, Toronto, ON"
    url = FLOORPLANS_URL

    async def _start_browser(self, playwright):
        """Stealth browser to pass Cloudflare."""
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-CA",
        )
        await self._context.add_init_script("""
            delete Object.getPrototypeOf(navigator).webdriver;
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        """)

    async def _do_scrape(self) -> list[UnitData]:
        units = await self._scrape_httpx()
        if units is None:
            logger.info("[The Montgomery] httpx blocked — falling back to Playwright")
            units = await self._scrape_playwright()
        return units or []

    async def _scrape_httpx(self):
        """Returns list or None if blocked."""
        seen = set()
        units = []
        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            test = await client.get(FP_URLS[0])
            if test.status_code == 403:
                logger.info("[The Montgomery] httpx got 403 — IP blocked")
                return None
            for fp_url in FP_URLS:
                try:
                    resp = await client.get(fp_url)
                    if resp.status_code != 200:
                        continue
                    new = [u for u in self._parse_html(resp.text, fp_url) if u.unit_number not in seen]
                    for u in new:
                        seen.add(u.unit_number)
                    units.extend(new)
                    logger.info(f"[The Montgomery] httpx {fp_url.split('/')[-1]}: {len(new)} unit(s)")
                except Exception as e:
                    logger.error(f"[The Montgomery] httpx error {fp_url}: {e}")
        logger.info(f"[The Montgomery] httpx total: {len(units)}")
        return units

    async def _scrape_playwright(self):
        """Playwright fallback — pass Cloudflare once, then fetch all pages in parallel."""
        seen = set()
        units = []
        page = await self._new_page()

        try:
            # Step 1: Navigate to main page and wait for Cloudflare to fully clear
            await page.goto(FLOORPLANS_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)

            # Poll until "Just a moment..." resolves (up to 20s)
            for _ in range(20):
                title = await page.title()
                if "moment" not in title.lower() and "security" not in title.lower() and "verify" not in title.lower():
                    break
                logger.info(f"[The Montgomery] Waiting for Cloudflare: {title}")
                await page.wait_for_timeout(1000)

            title = await page.title()
            logger.info(f"[The Montgomery] Playwright ready: {title}")

            if "moment" in title.lower() or "verify" in title.lower():
                logger.error("[The Montgomery] Cloudflare not cleared after 20s")
                return []

            # Step 2: Fetch all 8 pages IN PARALLEL using browser cookies
            # fetch() sends Cloudflare cookies — no new challenge per page
            # This is ~2 seconds total vs 40+ seconds with page.goto() per page
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
                            return {url, html, status: r.status};
                        } catch(e) {
                            return {url, html: '', status: 0, error: e.message};
                        }
                    }));
                }
            """)

            logger.info(f"[The Montgomery] Fetched {len(raw_results)} pages in parallel")

            for result in raw_results:
                fp_url = result['url']
                status = result.get('status', 0)
                html   = result.get('html', '')

                if status != 200 or not html:
                    logger.debug(f"[The Montgomery] {fp_url.split('/')[-1]}: status {status}")
                    continue

                new = [u for u in self._parse_html(html, fp_url) if u.unit_number not in seen]
                for u in new:
                    seen.add(u.unit_number)
                units.extend(new)
                logger.info(f"[The Montgomery] {fp_url.split('/')[-1]}: {len(new)} unit(s)")

        except Exception as e:
            logger.error(f"[The Montgomery] Playwright fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Montgomery] Playwright total: {len(units)}")
        return units

    def _parse_html(self, html: str, fp_url: str) -> list[UnitData]:
        soup = BeautifulSoup(html, "lxml")
        units = []

        h1 = soup.find("h1")
        fp_name = h1.get_text(strip=True) if h1 else fp_url.split("/")[-1]

        text = soup.get_text(separator=" ")
        bed_m  = re.search(r"(\d+)\s*Bedroom", text, re.IGNORECASE)
        bath_m = re.search(r"(\d+(?:\.\d)?)\s*Bathroom", text, re.IGNORECASE)
        sqft_m = (re.search(r"Up to ([\d,]+)\s*Sq", text, re.IGNORECASE) or
                  re.search(r"([\d,]+)\s*Sq\.\s*Ft", text, re.IGNORECASE))

        beds      = int(bed_m.group(1))                  if bed_m  else -1
        bathrooms = float(bath_m.group(1))               if bath_m else None
        sqft      = int(sqft_m.group(1).replace(",","")) if sqft_m else None
        unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds, "Unknown")

        for card in soup.find_all("div", class_="card-body"):
            if "Apartment:" not in card.get_text():
                continue
            card_text = card.get_text(separator=" ", strip=True)
            apt_m  = re.search(r"Apartment:\s*#\s*(\w+)", card_text, re.IGNORECASE)
            date_m = re.search(r"Date Available:\s*([\d/]+)", card_text, re.IGNORECASE)
            rent_m = re.search(r"Starting at:\s*\$([\d,]+)\s*/Month", card_text, re.IGNORECASE)

            if not apt_m:
                continue
            unit_num = apt_m.group(1).strip()
            try:
                rent = float(rent_m.group(1).replace(",","")) if rent_m else None
            except Exception:
                rent = None
            if not rent or rent < 500:
                continue

            avail_raw = date_m.group(1) if date_m else None
            if avail_raw:
                m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", avail_raw)
                if m:
                    from datetime import datetime
                    try:
                        dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                        avail_str = dt.strftime("%b {}, %Y").format(dt.day)
                    except Exception:
                        avail_str = avail_raw
                else:
                    avail_str = avail_raw
            else:
                avail_str = "Available Now"

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

        return units
