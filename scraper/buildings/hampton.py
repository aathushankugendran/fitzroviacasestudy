"""
The Hampton — 101 Roehampton Avenue
Scrapes from:
  1. WordPress REST API: /wp-json/wp/v2/project?per_page=100
  2. Penthouse page DOM for any additional floor plans

Uses httpx directly — no Playwright needed.
"""

import re
import json
import httpx
from loguru import logger
from scraper.base import BaseScraper, UnitData

FLOORPLANS_URL  = "https://thehampton.ca/floorplans/"
PENTHOUSE_URL   = "https://thehampton.ca/penthouse-collection/"
WP_API_URL      = "https://thehampton.ca/wp-json/wp/v2/project?per_page=100&_fields=id,title,excerpt"

STARTING_PRICES = {
    "1-Bed":     2125.0,
    "1-Bed+Den": 2750.0,
    "2-Bed":     3300.0,
    "3-Bed":     3995.0,
}
BATH_MAP = {
    "1-Bed":     1.0,
    "1-Bed+Den": 1.0,
    "2-Bed":     2.0,
    "3-Bed":     2.0,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class HamptonScraper(BaseScraper):
    building_name = "The Hampton"
    building_address = "101 Roehampton Avenue, Toronto, ON"
    url = FLOORPLANS_URL

    async def _do_scrape(self) -> list[UnitData]:
        units = []
        seen = set()

        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            # Step 1: WordPress REST API
            try:
                resp = await client.get(WP_API_URL)
                logger.info(f"[The Hampton] WP API status: {resp.status_code}")
                projects = resp.json()
                logger.info(f"[The Hampton] WP API: {len(projects)} floor plans")

                for proj in projects:
                    title = proj.get("title", {}).get("rendered", "").strip()
                    excerpt_html = proj.get("excerpt", {}).get("rendered", "")
                    excerpt = re.sub(r"<[^>]+>", "", excerpt_html).strip()

                    if title in seen:
                        continue
                    seen.add(title)

                    unit = self._parse_project(title, excerpt, FLOORPLANS_URL)
                    if unit:
                        units.append(unit)
                        logger.debug(f"[The Hampton] ✓ {title} | {unit.unit_type} | "
                                     f"{unit.sq_ft}sqft | ${unit.monthly_rent}")

            except Exception as e:
                logger.error(f"[The Hampton] WP API failed: {e}")

            # Step 2: Penthouse page via httpx + BeautifulSoup
            try:
                from bs4 import BeautifulSoup
                resp2 = await client.get(PENTHOUSE_URL)
                soup = BeautifulSoup(resp2.text, "lxml")

                for card in soup.select(".pp-post-wrap"):
                    name_el    = card.select_one(".pp-post-title")
                    excerpt_el = card.select_one(".pp-post-excerpt")
                    if not name_el or not excerpt_el:
                        continue
                    title   = name_el.get_text(strip=True)
                    excerpt = excerpt_el.get_text(strip=True)
                    if title in seen:
                        continue
                    seen.add(title)
                    unit = self._parse_project(title, excerpt, PENTHOUSE_URL)
                    if unit:
                        units.append(unit)

                logger.info(f"[The Hampton] Penthouse page scraped")

            except Exception as e:
                logger.error(f"[The Hampton] Penthouse page failed: {e}")

        logger.info(f"[The Hampton] Total: {len(units)} floor plans")
        return units

    def _parse_project(self, title: str, excerpt: str, source_url: str) -> UnitData | None:
        try:
            sqft_m  = re.search(r"([\d,]+)\s*sq\.ft", excerpt, re.IGNORECASE)
            sqft    = int(sqft_m.group(1).replace(",","")) if sqft_m else None
            has_den = bool(re.search(r"\+\s*den", excerpt, re.IGNORECASE))
            bed_m   = re.search(r"(\d+)\s*Bedroom", excerpt, re.IGNORECASE)

            if bed_m:
                bedrooms = int(bed_m.group(1))
                type_key = f"{bedrooms}-Bed+Den" if has_den else f"{bedrooms}-Bed"
                unit_type = f"{bedrooms}-Bed"
            else:
                return None

            rent      = STARTING_PRICES.get(type_key) or STARTING_PRICES.get(f"{bedrooms}-Bed")
            bathrooms = BATH_MAP.get(type_key) or BATH_MAP.get(f"{bedrooms}-Bed")
            if not rent:
                return None

            return UnitData(
                unit_type=unit_type,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                floor_plan_name=title,
                sq_ft=sqft,
                monthly_rent=rent,
                available_date="Available Now",
                incentives=None,
                source_url=source_url,
            )
        except Exception as e:
            logger.debug(f"[The Hampton] Parse error {title}: {e}")
            return None
