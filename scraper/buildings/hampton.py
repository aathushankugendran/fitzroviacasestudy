"""
The Hampton — 101 Roehampton Avenue
Scrapes from two pages:
  1. https://thehampton.ca/floorplans/    → standard suites
  2. https://thehampton.ca/penthouse-collection/ → penthouse units

Data source: WordPress REST API (/wp-json/wp/v2/project) returns
all floor plans as 'project' post type with title + excerpt.

Confirmed floor plans (12 standard + 3 penthouse):
  WordPress API excerpt format: "N Bedroom | NNN sq.ft" or "N Bedroom + Den | NNN sq.ft"

Starting prices from filter buttons (confirmed from page):
  1 Bedroom:        from $2,125
  1 Bedroom + Den:  from $2,750
  2 Bedroom:        from $3,300
  3 Bedroom:        from $3,995

Bathroom counts: inferred from bedroom count
  (not available in site text/API — only in floor plan images)
  1 Bed → 1 Bath
  1 Bed + Den → 1 Bath
  2 Bed → 2 Bath
  3 Bed → 2 Bath (penthouse: 2 Bath)
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

FLOORPLANS_URL  = "https://thehampton.ca/floorplans/"
PENTHOUSE_URL   = "https://thehampton.ca/penthouse-collection/"
WP_API_URL      = "https://thehampton.ca/wp-json/wp/v2/project?per_page=100&_fields=id,title,excerpt"

# Starting prices from confirmed filter buttons
STARTING_PRICES = {
    "1-Bed":        2125.0,
    "1-Bed+Den":    2750.0,
    "2-Bed":        3300.0,
    "3-Bed":        3995.0,
}

# Bath counts inferred (not available in site data)
BATH_MAP = {
    "1-Bed":     1.0,
    "1-Bed+Den": 1.0,
    "2-Bed":     2.0,
    "3-Bed":     2.0,
    "Bachelor":  1.0,
}


class HamptonScraper(BaseScraper):
    building_name = "The Hampton"
    building_address = "101 Roehampton Avenue, Toronto, ON"
    url = FLOORPLANS_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(10_000)
        units = []
        seen = set()

        try:
            # Use WordPress REST API — fastest and most reliable
            await page.goto(WP_API_URL, wait_until="domcontentloaded", timeout=15000)
            import json
            raw = await page.inner_text("body")
            projects = json.loads(raw)

            logger.info(f"[The Hampton] WP API: {len(projects)} floor plans")

            for proj in projects:
                title = proj.get("title", {}).get("rendered", "").strip()
                excerpt_html = proj.get("excerpt", {}).get("rendered", "")
                excerpt = re.sub(r"<[^>]+>", "", excerpt_html).strip()
                # excerpt = "1 Bedroom | 486 sq.ft" or "1 Bedroom + Den | 715 sq.ft"

                if title in seen:
                    continue
                seen.add(title)

                unit = self._parse_project(title, excerpt, FLOORPLANS_URL)
                if unit:
                    units.append(unit)
                    logger.debug(
                        f"[The Hampton] ✓ {title} | {unit.unit_type} | "
                        f"{unit.sq_ft}sqft | ${unit.monthly_rent} | {unit.bathrooms}bath"
                    )

            # Penthouse page — check for additional floor plans not in main API
            await page.goto(PENTHOUSE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(1500)

            penthouse_cards = await page.evaluate("""
                () => Array.from(document.querySelectorAll('.pp-post-wrap')).map(card => ({
                    name: card.querySelector('.pp-post-title')?.innerText?.trim() || '',
                    excerpt: card.querySelector('.pp-post-excerpt')?.innerText?.trim() || ''
                })).filter(c => c.name && c.excerpt)
            """)

            logger.info(f"[The Hampton] Penthouse page: {len(penthouse_cards)} cards")

            for card in penthouse_cards:
                title = card.get("name", "").strip()
                excerpt = card.get("excerpt", "").strip()
                if title in seen:
                    continue
                seen.add(title)
                unit = self._parse_project(title, excerpt, PENTHOUSE_URL)
                if unit:
                    units.append(unit)

        except Exception as e:
            logger.error(f"[The Hampton] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Hampton] Total: {len(units)} floor plans")
        return units

    def _parse_project(self, title: str, excerpt: str, source_url: str) -> UnitData | None:
        """
        Parse a floor plan from title + excerpt.
        excerpt format: "N Bedroom | NNN sq.ft" or "N Bedroom + Den | NNN sq.ft"
        """
        try:
            # Sqft
            sqft_m = re.search(r"([\d,]+)\s*sq\.ft", excerpt, re.IGNORECASE)
            sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None

            # Bed type
            has_den = bool(re.search(r"\+\s*den", excerpt, re.IGNORECASE))
            bed_m = re.search(r"(\d+)\s*Bedroom", excerpt, re.IGNORECASE)
            studio_m = re.search(r"studio|bachelor", excerpt, re.IGNORECASE)

            if studio_m:
                bedrooms, unit_type = 0, "Bachelor"
            elif bed_m:
                bedrooms = int(bed_m.group(1))
                if has_den:
                    unit_type = f"{bedrooms}-Bed"
                    type_key = f"{bedrooms}-Bed+Den"
                else:
                    unit_type = f"{bedrooms}-Bed"
                    type_key = f"{bedrooms}-Bed"
            else:
                return None

            type_key = f"{bedrooms}-Bed+Den" if has_den else f"{bedrooms}-Bed"
            rent = STARTING_PRICES.get(type_key) or STARTING_PRICES.get(f"{bedrooms}-Bed")
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
            logger.debug(f"[The Hampton] Parse error for {title}: {e}")
            return None