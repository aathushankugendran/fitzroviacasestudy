"""
The Montgomery — 2388 Yonge Street
Website: themontgomery.ca/floorplans

Strategy: Try httpx first (fast, works locally).
If blocked (403), fall back to Playwright (works on Railway/servers).

This ensures it works in BOTH environments.
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
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.themontgomery.ca/floorplans",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


class MontgomeryScraper(BaseScraper):
    building_name = "The Montgomery"
    building_address = "2388 Yonge Street, Toronto, ON"
    url = FLOORPLANS_URL

    async def _do_scrape(self) -> list[UnitData]:
        # Try httpx first (fast, works locally)
        units = await self._scrape_httpx()

        # If blocked, fall back to Playwright
        if units is None:
            logger.info("[The Montgomery] httpx blocked — falling back to Playwright")
            units = await self._scrape_playwright()

        return units or []

    async def _scrape_httpx(self):
        """Returns list of units, or None if blocked (403)."""
        units = []
        seen_units = set()

        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            # Test one page first to check if we're blocked
            test = await client.get(FP_URLS[0])
            if test.status_code == 403:
                logger.info("[The Montgomery] httpx got 403 — IP blocked")
                return None

            # Scrape all pages
            for fp_url in FP_URLS:
                try:
                    resp = await client.get(fp_url)
                    if resp.status_code != 200:
                        logger.debug(f"[The Montgomery] httpx {fp_url.split('/')[-1]}: {resp.status_code}")
                        continue

                    parsed = self._parse_html(resp.text, fp_url)
                    new_units = [u for u in parsed if u.unit_number not in seen_units]
                    for u in new_units:
                        seen_units.add(u.unit_number)
                    units.extend(new_units)
                    logger.info(f"[The Montgomery] httpx {fp_url.split('/')[-1]}: {len(new_units)} unit(s)")

                except Exception as e:
                    logger.error(f"[The Montgomery] httpx error on {fp_url}: {e}")

        logger.info(f"[The Montgomery] httpx total: {len(units)}")
        return units

    async def _scrape_playwright(self):
        """Playwright fallback for when httpx is blocked."""
        units = []
        seen_units = set()
        page = await self._new_page()

        try:
            # Navigate to main page to establish session / pass Cloudflare
            await page.goto(FLOORPLANS_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(3000)

            title = await page.title()
            logger.info(f"[The Montgomery] Playwright title: {title}")
            if "security" in title.lower() or "verify" in title.lower():
                logger.error("[The Montgomery] Cloudflare challenge not passed")
                return []

            # Navigate to each floor plan page
            for fp_url in FP_URLS:
                try:
                    await page.goto(fp_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500)
                    html = await page.content()
                    parsed = self._parse_html(html, fp_url)
                    new_units = [u for u in parsed if u.unit_number not in seen_units]
                    for u in new_units:
                        seen_units.add(u.unit_number)
                    units.extend(new_units)
                    logger.info(f"[The Montgomery] Playwright {fp_url.split('/')[-1]}: {len(new_units)} unit(s)")
                except Exception as e:
                    logger.error(f"[The Montgomery] Playwright error on {fp_url}: {e}")

        except Exception as e:
            logger.error(f"[The Montgomery] Playwright fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Montgomery] Playwright total: {len(units)}")
        return units

    def _parse_html(self, html: str, fp_url: str) -> list[UnitData]:
        """Parse apartment cards from floor plan page HTML."""
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
            # CRITICAL: space before /Month → "$2,812 /Month"
            rent_m = re.search(r"Starting at:\s*\$([\d,]+)\s*/Month", card_text, re.IGNORECASE)

            if not apt_m:
                continue

            unit_num = apt_m.group(1).strip()
            avail_raw = date_m.group(1) if date_m else None
            avail_str = self._parse_date(avail_raw) if avail_raw else "Available Now"

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
                available_date=avail_str,
                incentives=None,
                source_url=fp_url,
            ))
            logger.debug(f"[The Montgomery] ✓ #{unit_num} | {fp_name} | {unit_type} | ${rent}")

        return units

    def _parse_date(self, raw: str) -> str:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(raw).strip())
        if m:
            try:
                from datetime import datetime
                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return dt.strftime("%b %-d, %Y")
            except Exception:
                return raw
        return raw
