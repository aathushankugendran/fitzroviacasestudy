"""
The Montgomery — 2388 Yonge Street
RentCafe Property ID: 1310326

CONFIRMED APPROACH (Apr 28 2026):
- The data is server-rendered HTML by RentCafe platform
- RentCafe API: rentcafe.com/rentcafeapi.aspx?requestType=apartmentavailability&PropertyId=1310326
- This API cannot be called from Chrome (CORS) but CAN be called from Railway server (no CORS)
- httpx on themontgomery.ca gets 403 (Cloudflare blocks server IPs on the main domain)
- But rentcafe.com API itself does NOT have Cloudflare — direct httpx should work

Strategy:
1. Try RentCafe API directly (works from server, no CORS, no Cloudflare)
2. Fallback: httpx to themontgomery.ca floor plan pages
3. Fallback: Playwright with browser warming
"""

import re
import json
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from scraper.base import BaseScraper, UnitData

PROPERTY_ID    = "1310326"
FLOORPLANS_URL = "https://www.themontgomery.ca/floorplans"

RENTCAFE_API_URLS = [
    f"https://www.rentcafe.com/rentcafeapi.aspx?requestType=apartmentavailability&PropertyId={PROPERTY_ID}&APISource=1",
    f"https://api.rentcafe.com/rentcafeapi.aspx?requestType=apartmentavailability&PropertyId={PROPERTY_ID}",
    f"https://www.rentcafe.com/rentcafeapi.aspx?requestType=apartmentavailability&PropertyId={PROPERTY_ID}",
]

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

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Referer": "https://www.themontgomery.ca/",
}

PAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://www.themontgomery.ca/floorplans",
}


class MontgomeryScraper(BaseScraper):
    building_name = "The Montgomery"
    building_address = "2388 Yonge Street, Toronto, ON"
    url = FLOORPLANS_URL

    async def _start_browser(self, playwright):
        """Stealth browser."""
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
        """)

    async def _do_scrape(self) -> list[UnitData]:
        # Step 1: Try RentCafe API directly (no Cloudflare on rentcafe.com itself)
        logger.info("[The Montgomery] Trying RentCafe API directly...")
        units = await self._try_rentcafe_api()
        if units:
            logger.info(f"[The Montgomery] RentCafe API success: {len(units)} units")
            return units

        # Step 2: Try httpx to floor plan pages
        logger.info("[The Montgomery] Trying httpx to floor plan pages...")
        units = await self._try_httpx_pages()
        if units:
            logger.info(f"[The Montgomery] httpx pages success: {len(units)} units")
            return units

        # Step 3: Playwright fallback
        logger.info("[The Montgomery] Trying Playwright fallback...")
        units = await self._try_playwright()
        return units or []

    async def _try_rentcafe_api(self) -> list[UnitData]:
        """Call RentCafe API directly — no CORS from server, no Cloudflare on rentcafe.com."""
        units = []
        async with httpx.AsyncClient(headers=API_HEADERS, timeout=15, follow_redirects=True) as client:
            for api_url in RENTCAFE_API_URLS:
                try:
                    resp = await client.get(api_url)
                    logger.info(f"[The Montgomery] RentCafe API {api_url.split('?')[0].split('/')[-1]}: status {resp.status_code}, len {len(resp.text)}")

                    if resp.status_code != 200 or not resp.text.strip():
                        continue

                    data = resp.json()
                    if not isinstance(data, list) or not data:
                        continue

                    # Check we got actual unit data
                    if "Error" in str(data[0]):
                        logger.debug(f"[The Montgomery] API error: {data[0]}")
                        continue

                    logger.info(f"[The Montgomery] RentCafe API returned {len(data)} units")
                    units = self._parse_rentcafe_api(data)
                    if units:
                        return units

                except Exception as e:
                    logger.debug(f"[The Montgomery] RentCafe API error: {e}")

        return units

    def _parse_rentcafe_api(self, data: list) -> list[UnitData]:
        """Parse RentCafe availability API response."""
        units = []
        seen = set()
        for item in data:
            try:
                unit_num  = str(item.get("UnitID") or item.get("ApartmentId") or "").strip()
                fp_name   = (item.get("FloorplanName") or item.get("Floorplan") or "").strip()
                beds_raw  = item.get("Beds") or item.get("Bedrooms") or -1
                baths_raw = item.get("Baths") or item.get("Bathrooms")
                sqft_raw  = item.get("SQFT") or item.get("SquareFootage")
                rent_raw  = item.get("Rent") or item.get("MinimumRent") or item.get("EffectiveRent")
                avail_raw = item.get("AvailableDate") or item.get("DateAvailable")

                if not unit_num or unit_num in seen:
                    continue
                seen.add(unit_num)

                try:
                    beds = int(beds_raw)
                except Exception:
                    beds = -1

                unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")
                bathrooms = float(baths_raw) if baths_raw else None
                sqft      = int(str(sqft_raw).replace(",","")) if sqft_raw else None

                try:
                    rent = float(str(rent_raw).replace("$","").replace(",",""))
                except Exception:
                    continue
                if rent < 500:
                    continue

                avail_str = self._parse_date(str(avail_raw)) if avail_raw else "Available Now"

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
                    source_url=FLOORPLANS_URL,
                ))
                logger.debug(f"[The Montgomery] API ✓ #{unit_num} | {fp_name} | {unit_type} | ${rent}")

            except Exception as e:
                logger.debug(f"[The Montgomery] API parse error: {e}")

        return units

    async def _try_httpx_pages(self) -> list[UnitData]:
        """Direct httpx to floor plan pages — works locally, sometimes on Railway."""
        seen = set()
        units = []
        async with httpx.AsyncClient(headers=PAGE_HEADERS, timeout=20, follow_redirects=True) as client:
            test = await client.get(FP_URLS[0])
            if test.status_code == 403:
                logger.info("[The Montgomery] httpx pages: 403, Cloudflare blocking")
                return []
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
                    logger.debug(f"[The Montgomery] httpx error: {e}")
        return units

    async def _try_playwright(self) -> list[UnitData]:
        """Playwright fallback — wait for Cloudflare then fetch all pages."""
        page = await self._new_page()
        units = []
        seen = set()
        try:
            await page.goto(FLOORPLANS_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            for i in range(30):
                title = await page.title()
                if not any(x in title.lower() for x in ["moment", "verify", "security"]):
                    logger.info(f"[The Montgomery] Playwright: Cloudflare cleared at {i}s")
                    break
                logger.info(f"[The Montgomery] Playwright: Cloudflare wait {i}s")
                await page.wait_for_timeout(1000)
            else:
                logger.error("[The Montgomery] Playwright: Cloudflare never cleared")
                return []

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
                            return {url, html: await r.text(), status: r.status};
                        } catch(e) {
                            return {url, html: '', status: 0, error: e.message};
                        }
                    }));
                }
            """)

            for result in raw_results:
                if result.get('status') != 200 or not result.get('html'):
                    continue
                new = [u for u in self._parse_html(result['html'], result['url']) if u.unit_number not in seen]
                for u in new:
                    seen.add(u.unit_number)
                units.extend(new)
                logger.info(f"[The Montgomery] Playwright {result['url'].split('/')[-1]}: {len(new)} unit(s)")

        except Exception as e:
            logger.error(f"[The Montgomery] Playwright fatal: {e}")
        finally:
            await page.close()

        return units

    def _parse_html(self, html: str, fp_url: str) -> list[UnitData]:
        soup = BeautifulSoup(html, "lxml")
        units = []
        h1 = soup.find("h1")
        fp_name = h1.get_text(strip=True) if h1 else fp_url.split("/")[-1]
        text = soup.get_text(separator=" ")
        bed_m  = re.search(r"(\d+)\s*Bedroom", text, re.IGNORECASE)
        bath_m = re.search(r"(\d+(?:\.\d)?)\s*Bathroom", text, re.IGNORECASE)
        sqft_m = re.search(r"Up to ([\d,]+)\s*Sq", text, re.IGNORECASE) or re.search(r"([\d,]+)\s*Sq\.\s*Ft", text, re.IGNORECASE)
        beds      = int(bed_m.group(1)) if bed_m else -1
        bathrooms = float(bath_m.group(1)) if bath_m else None
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
            try:
                rent = float(rent_m.group(1).replace(",","")) if rent_m else None
            except Exception:
                rent = None
            if not rent or rent < 500:
                continue
            units.append(UnitData(
                unit_number=apt_m.group(1).strip(),
                unit_type=unit_type, bedrooms=beds, bathrooms=bathrooms,
                floor_plan_name=fp_name, sq_ft=sqft, monthly_rent=rent,
                available_date=self._parse_date(date_m.group(1)) if date_m else "Available Now",
                incentives=None, source_url=fp_url,
            ))
        return units

    def _parse_date(self, raw: str) -> str:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(raw).strip())
        if m:
            try:
                from datetime import datetime
                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return dt.strftime("%b {}, %Y").format(dt.day)
            except Exception:
                return raw
        return raw
