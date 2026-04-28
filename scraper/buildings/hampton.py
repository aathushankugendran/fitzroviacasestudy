"""
The Hampton — 101 Roehampton Avenue
WordPress REST API: /wp-json/wp/v2/project

ISSUE ON RAILWAY: API returns status 202 with empty body (not 200).
FIX: Check response text before parsing JSON. If empty, scrape HTML page directly.

Confirmed 12 floor plans from API when working correctly.
"""

import re
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from scraper.base import BaseScraper, UnitData

FLOORPLANS_URL = "https://thehampton.ca/floorplans/"
WP_API_URL     = "https://thehampton.ca/wp-json/wp/v2/project?per_page=100&_fields=id,title,excerpt"

STARTING_PRICES = {"1-Bed": 2125.0, "1-Bed+Den": 2750.0, "2-Bed": 3300.0, "3-Bed": 3995.0}
BATH_MAP        = {"1-Bed": 1.0, "1-Bed+Den": 1.0, "2-Bed": 2.0, "3-Bed": 2.0}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}


class HamptonScraper(BaseScraper):
    building_name = "The Hampton"
    building_address = "101 Roehampton Avenue, Toronto, ON"
    url = FLOORPLANS_URL

    async def _do_scrape(self) -> list[UnitData]:
        units = []

        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            # Try WordPress REST API first
            units = await self._try_wp_api(client)

            # If API failed, fall back to scraping the HTML page
            if not units:
                logger.info("[The Hampton] API failed — falling back to HTML scrape")
                units = await self._try_html_scrape(client)

        logger.info(f"[The Hampton] Total: {len(units)} floor plans")
        return units

    async def _try_wp_api(self, client) -> list[UnitData]:
        units = []
        try:
            resp = await client.get(WP_API_URL)
            logger.info(f"[The Hampton] WP API status: {resp.status_code}")

            text = resp.text.strip()
            if not text or text == "null" or resp.status_code not in (200, 201):
                logger.warning(f"[The Hampton] WP API empty/bad response: status={resp.status_code} len={len(text)}")
                return []

            projects = resp.json()
            if not isinstance(projects, list):
                logger.warning(f"[The Hampton] WP API unexpected format: {type(projects)}")
                return []

            logger.info(f"[The Hampton] WP API: {len(projects)} floor plans")
            seen = set()
            for proj in projects:
                title   = proj.get("title", {}).get("rendered", "").strip()
                excerpt = re.sub(r"<[^>]+>", "", proj.get("excerpt", {}).get("rendered", "")).strip()
                if title in seen:
                    continue
                seen.add(title)
                unit = self._parse(title, excerpt, FLOORPLANS_URL)
                if unit:
                    units.append(unit)
                    logger.debug(f"[The Hampton] ✓ {title} | {unit.unit_type} | {unit.sq_ft}sqft | ${unit.monthly_rent}")

        except Exception as e:
            logger.error(f"[The Hampton] WP API error: {e}")

        return units

    async def _try_html_scrape(self, client) -> list[UnitData]:
        """Fallback: scrape the floor plans page HTML directly."""
        units = []
        try:
            resp = await client.get(FLOORPLANS_URL)
            soup = BeautifulSoup(resp.text, "lxml")
            seen = set()

            # Find floor plan entries — typically in article/post elements
            for el in soup.select("article, .pp-post, .elementor-post, .jet-listing-grid__item"):
                title_el   = el.select_one("h2, h3, h4, .entry-title, .pp-post-title")
                excerpt_el = el.select_one(".entry-content, .pp-post-excerpt, p")
                if not title_el:
                    continue
                title   = title_el.get_text(strip=True)
                excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""
                if not title or title in seen:
                    continue
                seen.add(title)
                unit = self._parse(title, excerpt, FLOORPLANS_URL)
                if unit:
                    units.append(unit)
                    logger.debug(f"[The Hampton] HTML ✓ {title} | {unit.unit_type}")

            logger.info(f"[The Hampton] HTML scrape: {len(units)} floor plans")

        except Exception as e:
            logger.error(f"[The Hampton] HTML scrape error: {e}")

        return units

    def _parse(self, title: str, excerpt: str, source_url: str) -> UnitData | None:
        try:
            sqft_m  = re.search(r"([\d,]+)\s*sq\.ft", excerpt, re.IGNORECASE)
            sqft    = int(sqft_m.group(1).replace(",","")) if sqft_m else None
            has_den = bool(re.search(r"\+\s*den", excerpt, re.IGNORECASE))
            bed_m   = re.search(r"(\d+)\s*Bedroom", excerpt, re.IGNORECASE)

            if not bed_m:
                return None

            bedrooms  = int(bed_m.group(1))
            type_key  = f"{bedrooms}-Bed+Den" if has_den else f"{bedrooms}-Bed"
            unit_type = f"{bedrooms}-Bed"
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
