"""
The Selby — 25 Selby Street
Direct API: https://triconliving.com/api/v1/apartments/the-selby

Confirmed field names from live API inspection:
  units[]:
    unit_code       → unit number (e.g. "2607")
    unit_type_code  → floor plan code (e.g. "sel_a13")
    beds            → int (1, 2, 3)
    baths           → string float (e.g. "1.0")
    floor           → int (e.g. 26)
    sqft            → int (e.g. 603)
    min_rent        → int (e.g. 2506) — lower bound of price range
    max_rent        → int (e.g. 2708) — upper bound of price range
    availability:
      date          → "2026-06-07" or null
      display       → "Available" or "Coming Soon"
    status          → "Vacant Unrented Ready", "Notice Unrented", etc.

  floorplans[]:
    title           → floor plan name (e.g. "A13")
    beds / baths / min_sqft / max_sqft

  concessions[]    → incentives/promos
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

API_URL  = "https://triconliving.com/api/v1/apartments/the-selby"
PAGE_URL = "https://triconliving.com/apartment/the-selby/#your-perfect-layout"


class SelbyScraper(BaseScraper):
    building_name = "The Selby"
    building_address = "25 Selby Street, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(8_000)
        units = []
        api_data = {}

        async def capture(response):
            if (response.status == 200 and
                    "api/v1/apartments/the-selby" in response.url and
                    "gallery" not in response.url):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = await response.json()
                        if isinstance(data, dict) and "units" in data:
                            api_data.update(data)
                            logger.info(f"[The Selby] API captured: {len(data.get('units', []))} units, {len(data.get('floorplans', []))} floorplans")
                except Exception as e:
                    logger.debug(f"[The Selby] API capture: {e}")

        page.on("response", capture)

        try:
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(3000)

            if api_data:
                units = self._parse_api(api_data)
            else:
                logger.warning("[The Selby] API not captured — trying direct fetch")
                units = await self._fetch_api_direct(page)

        except Exception as e:
            logger.error(f"[The Selby] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Selby] Total: {len(units)} units")
        return units

    async def _fetch_api_direct(self, page) -> list[UnitData]:
        """Navigate directly to the API endpoint as fallback."""
        try:
            await page.goto(API_URL, wait_until="domcontentloaded", timeout=15000)
            raw = await page.inner_text("body")
            import json
            data = json.loads(raw)
            if isinstance(data, dict) and "units" in data:
                return self._parse_api(data)
        except Exception as e:
            logger.error(f"[The Selby] Direct API fetch: {e}")
        return []

    def _parse_api(self, data: dict) -> list[UnitData]:
        """
        Parse the triconliving API response.
        Uses exact confirmed field names from live inspection.
        """
        raw_units = data.get("units", [])
        floorplans = {fp["title"]: fp for fp in data.get("floorplans", [])}

        # Check for concessions (building-wide incentives)
        concessions = data.get("concessions", [])
        if concessions:
            logger.info(f"[The Selby] Concessions found: {concessions}")

        units = []
        for item in raw_units:
            try:
                # Unit number
                unit_num = str(item.get("unit_code", "")).strip()

                # Floor plan code → look up full name
                fp_code = item.get("unit_type_code", "")
                # Map code like "sel_a13" → find matching floorplan title "A13"
                fp_name = None
                for title, fp in floorplans.items():
                    if fp_code in fp.get("unit_type_codes", []):
                        fp_name = title
                        break
                if not fp_name and fp_code:
                    # Extract plan name from code e.g. "sel_a13" → "A13"
                    m = re.search(r"_([a-zA-Z]\d+[a-zA-Z]?)$", fp_code)
                    fp_name = m.group(1).upper() if m else fp_code

                # Beds / baths
                beds = item.get("beds", -1)
                if beds == 0:
                    unit_type = "Bachelor"
                elif beds == 1:
                    unit_type = "1-Bed"
                elif beds == 2:
                    unit_type = "2-Bed"
                elif beds == 3:
                    unit_type = "3-Bed"
                else:
                    unit_type = "Unknown"

                baths_raw = item.get("baths", "")
                try:
                    bathrooms = float(baths_raw) if baths_raw else None
                except (ValueError, TypeError):
                    bathrooms = None

                # Sqft / floor
                sqft = item.get("sqft")
                sqft = int(sqft) if sqft else None
                floor = item.get("floor")
                floor = int(floor) if floor else None

                # Rent — use min_rent as the displayed price, store max too
                min_rent = item.get("min_rent")
                max_rent = item.get("max_rent")
                rent = float(min_rent) if min_rent else None
                rent_max = float(max_rent) if max_rent else None

                # Availability
                avail_obj = item.get("availability", {})
                avail_date = avail_obj.get("date")  # "2026-06-07" or null
                avail_display = avail_obj.get("display", "Available")  # "Available" or "Coming Soon"

                if avail_date:
                    # Format date nicely: "2026-06-07" → "Jun 7, 2026"
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(avail_date, "%Y-%m-%d")
                        avail_str = dt.strftime("%b %-d, %Y")
                    except Exception:
                        avail_str = avail_date
                else:
                    avail_str = avail_display or "Available"

                # Skip if no rent
                if not rent or rent < 500:
                    continue

                units.append(UnitData(
                    unit_number=unit_num or None,
                    unit_type=unit_type,
                    bedrooms=int(beds) if beds is not None and beds >= 0 else None,
                    bathrooms=bathrooms,
                    floor_plan_name=fp_name,
                    monthly_rent=rent,
                    rent_min=rent,
                    rent_max=rent_max,
                    sq_ft=sqft,
                    floor=floor,
                    available_date=avail_str,
                    incentives=None,  # filled by base.py live scrape
                    source_url=PAGE_URL,
                ))
                logger.debug(
                    f"[The Selby] ✓ #{unit_num} | {unit_type} | {fp_name} | "
                    f"Floor {floor} | {sqft}sqft | ${rent}-${rent_max} | {avail_str}"
                )

            except Exception as e:
                logger.debug(f"[The Selby] Unit parse: {e}")

        logger.info(f"[The Selby] Parsed {len(units)} of {len(raw_units)} units")
        return units