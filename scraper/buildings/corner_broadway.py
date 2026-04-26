"""
Corner on Broadway — 2300 Yonge Street
Website: thecornerrentals.com/suites
"""

import re
from bs4 import BeautifulSoup
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL = "https://thecornerrentals.com/suites"


class CornerBroadwayScraper(BaseScraper):
    building_name = "Corner on Broadway"
    building_address = "2300 Yonge Street, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(10_000)
        units = []

        try:
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(1500)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # Find the main floorplan table
            table = soup.find("table")
            if not table:
                logger.error("[Corner on Broadway] No table found on page")
                return []

            rows = table.find_all("tr")
            logger.info(f"[Corner on Broadway] Found {len(rows)} rows in table")

            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if not cells or cells[0].upper() in ("SUITE", ""):
                    continue  # skip header

                try:
                    # Columns: Suite | Bedroom(s) | Bathroom(s) | Int Sq.Ft. | Ext Sq.Ft. | Starting From
                    suite_name = cells[0] if len(cells) > 0 else ""
                    bed_raw    = cells[1] if len(cells) > 1 else ""
                    bath_raw   = cells[2] if len(cells) > 2 else ""
                    sqft_raw   = cells[3] if len(cells) > 3 else ""
                    price_raw  = cells[5] if len(cells) > 5 else ""

                    # Parse bed type
                    has_den = bool(re.search(r"\+\s*den|den", bed_raw, re.IGNORECASE))
                    junior  = bool(re.search(r"junior", bed_raw, re.IGNORECASE))
                    bed_m   = re.search(r"(\d+)", bed_raw)

                    if junior:
                        unit_type = "Bachelor"
                        bedrooms  = 0
                    elif bed_m:
                        bedrooms  = int(bed_m.group(1))
                        unit_type = f"{bedrooms}-Bed"
                    else:
                        continue

                    bathrooms = float(bath_raw) if bath_raw.replace(".","").isdigit() else None
                    sqft      = int(sqft_raw.replace(",","")) if sqft_raw.replace(",","").isdigit() else None

                    # Price: "$2150.00/mth" or "$2563.50/mth"
                    price_m = re.search(r"\$([\d,]+(?:\.\d+)?)", price_raw)
                    rent    = float(price_m.group(1).replace(",","")) if price_m else None

                    if not rent or rent < 500:
                        continue

                    units.append(UnitData(
                        unit_number=suite_name,
                        unit_type=unit_type,
                        bedrooms=bedrooms,
                        bathrooms=bathrooms,
                        sq_ft=sqft,
                        monthly_rent=rent,
                        available_date="Available Now",
                        incentives=None,
                        source_url=PAGE_URL,
                    ))
                    logger.debug(
                        f"[Corner on Broadway] ✓ {suite_name} | {unit_type} | "
                        f"{sqft}sqft | ${rent} | {bathrooms}bath"
                    )

                except Exception as e:
                    logger.debug(f"[Corner on Broadway] Row parse: {e}")

        except Exception as e:
            logger.error(f"[Corner on Broadway] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[Corner on Broadway] Total: {len(units)} suites")
        return units