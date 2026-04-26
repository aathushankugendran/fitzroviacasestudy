"""
Story of Midtown — 75 Broadway Avenue (Revitalized Suites)
Website: mystorymidtown.com/suites

CONFIRMED API (inspected live via Chrome):
  75 Broadway: https://website-gateway.rentsync.com/v1/6d6e564e-41a2-4754-8c0e-dca9f198110f/floorplan-navigator-v2?where=lang:en
  73 Broadway: https://website-gateway.rentsync.com/v1/e65cbbce-8097-4ae0-ac73-74cb0411c232/floorplan-navigator-v2?where=lang:en

We target 75 Broadway only (revitalized suites, ~102 total units).

Confirmed field names from live API (floorData[].units[]):
  number          → unit number e.g. "0107"
  bed             → int (0=Bachelor, 1, 2, 3)
  bath            → int (1, 2)
  floor           → string floor number e.g. "1"
  sqFt            → string e.g. "601"
  rate            → string rent e.g. "2279"
  typeName        → e.g. "1 Bedroom, 1 Bathroom"
  available       → 1 = available, 0 = not available
  availabilityDate → ISO date string or null
  availability    → status string or null
  den             → "yes"/"no"
"""

import re
import json
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL = "https://www.mystorymidtown.com/suites"
# 75 Broadway Rentsync API (confirmed from live Chrome network inspection)
API_75 = "https://website-gateway.rentsync.com/v1/6d6e564e-41a2-4754-8c0e-dca9f198110f/floorplan-navigator-v2?where=lang:en"


class StoryMidtownScraper(BaseScraper):
    building_name = "Story of Midtown"
    building_address = "75 Broadway Avenue, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(8_000)
        units = []
        api_raw = {}

        async def capture(response):
            if (response.status == 200 and
                    "6d6e564e-41a2-4754-8c0e-dca9f198110f" in response.url and
                    "floorplan-navigator-v2" in response.url):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        if isinstance(data, dict) and "floorData" in data:
                            api_raw.update(data)
                            floors = data.get("floorData", [])
                            total = sum(len(f.get("units", [])) for f in floors)
                            logger.info(f"[Story of Midtown] API captured: {len(floors)} floors, {total} units")
                except Exception as e:
                    logger.debug(f"[Story of Midtown] API capture: {e}")

        page.on("response", capture)

        try:
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(3000)

            if api_raw:
                units = self._parse_api(api_raw)
            else:
                # Fallback: fetch API directly
                logger.info("[Story of Midtown] XHR not captured — fetching API directly")
                await page.goto(API_75, wait_until="domcontentloaded", timeout=15000)
                raw_text = await page.inner_text("body")
                data = json.loads(raw_text)
                if "floorData" in data:
                    api_raw.update(data)
                    units = self._parse_api(api_raw)

        except Exception as e:
            logger.error(f"[Story of Midtown] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[Story of Midtown] Total available: {len(units)}")
        return units

    def _parse_api(self, data: dict) -> list[UnitData]:
        """
        Parse the Rentsync floorplan-navigator-v2 response.
        Uses exact confirmed field names from live Chrome inspection.
        """
        floor_data = data.get("floorData", [])
        units = []

        for floor_obj in floor_data:
            floor_label = floor_obj.get("floorLabel") or floor_obj.get("floorNumber")
            try:
                floor_num = int(floor_label) if floor_label else None
            except (ValueError, TypeError):
                floor_num = None

            raw_units = floor_obj.get("units", [])

            for item in raw_units:
                try:
                    # Only scrape available units
                    if item.get("available", 0) != 1:
                        continue

                    # Unit number
                    unit_num = str(item.get("number", "")).strip()

                    # Bedrooms → unit type
                    bed = item.get("bed", -1)
                    den = item.get("den", "no") == "yes"
                    if bed == 0:
                        unit_type = "Bachelor"
                        bedrooms = 0
                    elif bed == 1:
                        unit_type = "1-Bed"
                        bedrooms = 1
                    elif bed == 2:
                        unit_type = "2-Bed"
                        bedrooms = 2
                    elif bed == 3:
                        unit_type = "3-Bed"
                        bedrooms = 3
                    else:
                        unit_type = "Unknown"
                        bedrooms = -1

                    # Bathrooms
                    bath_raw = item.get("bath")
                    bathrooms = float(bath_raw) if bath_raw is not None else None

                    # Sqft
                    sqft_raw = item.get("sqFt")
                    try:
                        sqft = int(sqft_raw) if sqft_raw else None
                    except (ValueError, TypeError):
                        sqft = None

                    # Rent
                    rate_raw = item.get("rate")
                    try:
                        rent = float(rate_raw) if rate_raw else None
                    except (ValueError, TypeError):
                        rent = None

                    # Skip bad data
                    if not rent or rent < 500:
                        continue

                    # Floor plan name from typeName e.g. "1 Bedroom, 1 Bathroom"
                    type_name = item.get("typeName", "")

                    # Availability
                    avail_date_raw = item.get("availabilityDate")
                    avail_status = item.get("availability")

                    if avail_date_raw:
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(avail_date_raw[:10], "%Y-%m-%d")
                            avail_str = dt.strftime("%b %-d, %Y")
                        except Exception:
                            avail_str = avail_date_raw
                    elif avail_status:
                        avail_str = avail_status
                    else:
                        avail_str = "Available Now"

                    units.append(UnitData(
                        unit_number=unit_num or None,
                        unit_type=unit_type,
                        bedrooms=bedrooms,
                        bathrooms=bathrooms,
                        floor_plan_name=type_name or None,
                        sq_ft=sqft,
                        monthly_rent=rent,
                        floor=floor_num,
                        available_date=avail_str,
                        incentives=None,  # filled by base.py live scrape
                        source_url=PAGE_URL,
                    ))

                    logger.debug(
                        f"[Story of Midtown] ✓ Unit {unit_num} | {unit_type} | "
                        f"Floor {floor_num} | {sqft}sqft | ${rent} | {avail_str}"
                    )

                except Exception as e:
                    logger.debug(f"[Story of Midtown] Unit parse: {e}")

        available = [u for u in units if u.monthly_rent and u.monthly_rent > 500]
        logger.info(f"[Story of Midtown] Parsed {len(available)} available units across {len(floor_data)} floors")
        return available