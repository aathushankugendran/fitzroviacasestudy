"""
The Hampton — 101 Roehampton Avenue
WordPress REST API: /wp-json/wp/v2/project — returns 12 floor plans as JSON.

CONFIRMED (Apr 28 2026 via Chrome MCP):
- API returns 200 with 12 floor plans
- Excerpt format: "1 Bedroom | 486 sq.ft" or "1 Bedroom + Den | 715 sq.ft"
- HTML page has 9 floor plans (.pp-post cards)
- Accepts 200, 201, 202 status codes (Railway sometimes returns 202)
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
            units = await self._try_wp_api(client)
            if not units:
                logger.info("[The Hampton] API returned nothing — trying HTML scrape")
                units = await self._try_html_scrape(client)
        logger.info(f"[The Hampton] Total: {len(units)} floor plans")
        return units

    async def _try_wp_api(self, client) -> list[UnitData]:
        units = []
        try:
            resp = await client.get(WP_API_URL)
            logger.info(f"[The Hampton] WP API status: {resp.status_code}, len: {len(resp.text)}")
            text = resp.text.strip()

            # Accept 200, 201, 202 — Railway sometimes returns 202
            if not text or text in ("null", "[]") or resp.status_code >= 400:
                logger.warning(f"[The Hampton] WP API unusable: status={resp.status_code}")
                return []

            try:
                projects = resp.json()
            except Exception:
                logger.warning("[The Hampton] WP API response is not valid JSON")
                return []

            if not isinstance(projects, list) or not projects:
                return []

            logger.info(f"[The Hampton] WP API: {len(projects)} floor plans")
            seen = set()
            for proj in projects:
                title   = proj.get("title", {}).get("rendered", "").strip()
                excerpt = re.sub(r"<[^>]+>", "", proj.get("excerpt", {}).get("rendered", "")).strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                unit = self._parse(title, excerpt)
                if unit:
                    units.append(unit)
                    logger.debug(f"[The Hampton] ✓ {title} | {unit.unit_type} | {unit.sq_ft}sqft | ${unit.monthly_rent}")

        except Exception as e:
            logger.error(f"[The Hampton] WP API error: {e}")
        return units

    async def _try_html_scrape(self, client) -> list[UnitData]:
        units = []
        try:
            resp = await client.get(FLOORPLANS_URL)
            soup = BeautifulSoup(resp.text, "lxml")
            seen = set()
            for el in soup.select(".pp-post, article"):
                title_el   = el.select_one(".pp-post-title, h2, h3, h4")
                excerpt_el = el.select_one(".pp-post-excerpt, p")
                if not title_el:
                    continue
                title   = title_el.get_text(strip=True)
                excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""
                if not title or title in seen:
                    continue
                seen.add(title)
                unit = self._parse(title, excerpt)
                if unit:
                    units.append(unit)
                    logger.debug(f"[The Hampton] HTML ✓ {title} | {unit.unit_type}")
            logger.info(f"[The Hampton] HTML scrape: {len(units)} floor plans")
        except Exception as e:
            logger.error(f"[The Hampton] HTML scrape error: {e}")
        return units

    def _parse(self, title: str, excerpt: str) -> UnitData | None:
        try:
            # Match sqft: "486 sq.ft" or "486 sqft" or "486 sq ft"
            sqft_m  = re.search(r"([\d,]+)\s*sq", excerpt, re.IGNORECASE)
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
                source_url=FLOORPLANS_URL,
            )
        except Exception as e:
            logger.debug(f"[The Hampton] Parse error {title}: {e}")
            return None
