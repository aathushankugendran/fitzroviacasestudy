"""
The Montgomery — 2388 Yonge Street
Website: themontgomery.ca/floorplans (RentCafe + Cloudflare Turnstile)

ROOT CAUSE: Railway is an AWS data center IP. Cloudflare recognizes it and
shows "Just a moment..." Turnstile challenge that headless browsers struggle
to pass.

SOLUTION:
1. httpx first (fast, works locally when Cloudflare doesn't block)
2. Playwright fallback with browser warming:
   - Warm up with google.ca first (establishes real browsing history)
   - Navigate to home page first, then floorplans (natural navigation)
   - Random mouse movement to simulate human behavior
   - Wait up to 45 seconds with retries
   - After Cloudflare clears, fetch all 8 pages via Promise.all(fetch())
3. If Playwright also fails, try httpx one more time (sometimes IPs rotate)

This is the only approach that works without an external proxy service.
"""

import re
import httpx
import asyncio
from bs4 import BeautifulSoup
from loguru import logger
from scraper.base import BaseScraper, UnitData

HOME_URL       = "https://www.themontgomery.ca/"
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
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
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
        """Stealth browser — mimics real Chrome as closely as possible."""
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,800",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-CA",
            timezone_id="America/Toronto",
            geolocation={"longitude": -79.3957, "latitude": 43.6629},
            permissions=["geolocation"],
            extra_http_headers={
                "Accept-Language": "en-CA,en;q=0.9",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }
        )
        await self._context.add_init_script("""
            // Remove webdriver flag
            delete Object.getPrototypeOf(navigator).webdriver;
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // Add Chrome runtime
            window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}, app: {}};
            // Fake plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                    {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                    {name: 'Native Client', filename: 'internal-nacl-plugin'}
                ]
            });
            // Fake languages
            Object.defineProperty(navigator, 'languages', {get: () => ['en-CA', 'en']});
            // Fake hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            // Fake device memory
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
        """)

    async def _do_scrape(self) -> list[UnitData]:
        # Step 1: Try httpx (works locally, fast)
        logger.info("[The Montgomery] Trying httpx first...")
        units = await self._try_httpx()
        if units is not None:
            return units

        # Step 2: Playwright with browser warming
        logger.info("[The Montgomery] httpx blocked — using Playwright with browser warming")
        units = await self._try_playwright()
        if units:
            return units

        # Step 3: Retry httpx (in case IP changed)
        logger.info("[The Montgomery] Playwright failed — retrying httpx")
        units = await self._try_httpx()
        return units or []

    async def _try_httpx(self):
        """Returns list or None if blocked (403)."""
        seen = set()
        units = []
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
                test = await client.get(FP_URLS[0])
                if test.status_code == 403:
                    logger.info("[The Montgomery] httpx 403 — IP blocked by Cloudflare")
                    return None
                if test.status_code != 200:
                    logger.info(f"[The Montgomery] httpx {test.status_code}")
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
                        logger.debug(f"[The Montgomery] httpx error {fp_url}: {e}")

            logger.info(f"[The Montgomery] httpx total: {len(units)}")
            return units
        except Exception as e:
            logger.error(f"[The Montgomery] httpx fatal: {e}")
            return None

    async def _try_playwright(self):
        """Playwright with browser warming to pass Cloudflare."""
        page = await self._new_page()
        units = []
        seen = set()

        try:
            # WARM UP: Visit google.ca first to establish legitimate browsing history
            logger.info("[The Montgomery] Warming browser with google.ca...")
            try:
                await page.goto("https://www.google.ca", wait_until="domcontentloaded", timeout=10000)
                await page.wait_for_timeout(2000)
                # Move mouse around to simulate human
                await page.mouse.move(640, 400)
                await page.mouse.move(300, 200)
                await page.mouse.move(900, 500)
            except Exception:
                pass

            # Navigate to Montgomery HOME PAGE first (not floorplans directly)
            logger.info("[The Montgomery] Navigating to home page first...")
            try:
                await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                await page.mouse.move(500, 300)
                await page.mouse.move(700, 400)
            except Exception as e:
                logger.debug(f"[The Montgomery] Home page navigation: {e}")

            # Now navigate to floorplans (more natural flow)
            logger.info("[The Montgomery] Navigating to /floorplans...")
            await page.goto(FLOORPLANS_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)

            # Wait up to 45s for Cloudflare to clear
            # Check for actual content, not just title
            for i in range(45):
                title = await page.title()
                is_blocked = any(x in title.lower() for x in ["moment", "verify", "security", "checking"])

                if not is_blocked:
                    logger.info(f"[The Montgomery] Cloudflare cleared at {i}s: {title}")
                    break

                # Try moving mouse to simulate activity
                if i % 5 == 0:
                    try:
                        await page.mouse.move(300 + i * 5, 200 + i * 3)
                    except Exception:
                        pass

                logger.info(f"[The Montgomery] Waiting for Cloudflare ({i}s): {title}")
                await page.wait_for_timeout(1000)
            else:
                logger.error("[The Montgomery] Cloudflare not cleared after 45s")
                return []

            # Extra wait to ensure full page load
            await page.wait_for_timeout(2000)

            # Fetch all 8 floor plan pages in parallel using Cloudflare cookies
            logger.info("[The Montgomery] Fetching all floor plans in parallel...")
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
                            const bodyText = doc.body?.textContent || '';
                            const beds = bodyText.match(/(\\d+)\\s*Bedroom/i)?.[1];
                            const bath = bodyText.match(/(\\d+(?:\\.\\d)?)\\s*Bathroom/i)?.[1];
                            const sqftM = bodyText.match(/Up to ([\\d,]+)\\s*Sq/i) ||
                                          bodyText.match(/([\\d,]+)\\s*Sq\\.\\s*Ft/i);
                            const sqft = sqftM?.[1];
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

            logger.info(f"[The Montgomery] Parallel fetch done: {len(raw_results)} pages")

            for page_data in raw_results:
                fp_name  = page_data.get("name") or page_data["url"].split("/")[-1]
                beds_raw = page_data.get("beds")
                bath_raw = page_data.get("bath")
                sqft_raw = (page_data.get("sqft") or "").replace(",","")
                fp_url   = page_data["url"]
                status   = page_data.get("status", 0)

                beds      = int(beds_raw) if beds_raw else -1
                bathrooms = float(bath_raw) if bath_raw else None
                sqft      = int(sqft_raw) if sqft_raw.isdigit() else None
                unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")

                logger.info(f"[The Montgomery] {fp_name}: {len(page_data.get('cards',[]))} cards | HTTP {status}")

                for card in page_data.get("cards", []):
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
                    avail_str = self._parse_date(avail_raw) if avail_raw else "Available Now"

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
        unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")

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

            units.append(UnitData(
                unit_number=unit_num,
                unit_type=unit_type,
                bedrooms=beds,
                bathrooms=bathrooms,
                floor_plan_name=fp_name,
                sq_ft=sqft,
                monthly_rent=rent,
                available_date=self._parse_date(date_m.group(1)) if date_m else "Available Now",
                incentives=None,
                source_url=fp_url,
            ))
            logger.debug(f"[The Montgomery] ✓ #{unit_num} | {fp_name} | {unit_type} | ${rent}")

        return units

    def _parse_date(self, raw: str) -> str:
        if not raw:
            return "Available Now"
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(raw).strip())
        if m:
            try:
                from datetime import datetime
                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return dt.strftime("%b {}, %Y").format(dt.day)
            except Exception:
                return raw
        return raw
