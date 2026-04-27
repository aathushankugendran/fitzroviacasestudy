"""
The Selby — 25 Selby Street
Direct API: https://triconliving.com/api/v1/apartments/the-selby

Confirmed field names from live API inspection:
  units[]:
    unit_code, beds, baths, floor, sqft, min_rent, max_rent,
    availability: {date, display}, unit_type_code

  floorplans[]: title, beds, baths, min_sqft, max_sqft, unit_type_codes
"""

import re
import httpx
from loguru import logger
from scraper.base import BaseScraper, UnitData

API_URL  = "https://triconliving.com/api/v1/apartments/the-selby"
PAGE_URL = "https://triconliving.com/apartment/the-selby/#your-perfect-layout"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://triconliving.com/",
}


class SelbyScraper(BaseScraper):
    building_name = "The Selby"
    building_address = "25 Selby Street, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        units = []

        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
                resp = await client.get(API_URL)
                logger.info(f"[The Selby] API status: {resp.status_code}")

                if resp.status_code != 200:
                    logger.error(f"[The Selby] API returned {resp.status_code}")
                    return []

                data = resp.json()
                if not isinstance(data, dict) or "units" not in data:
                    logger.error(f"[The Selby] Unexpected response: {str(data)[:200]}")
                    return []

                logger.info(f"[The Selby] API returned {len(data.get('units', []))} units, "
                            f"{len(data.get('floorplans', []))} floorplans")
                units = self._parse_api(data)

        except Exception as e:
            logger.error(f"[The Selby] Fatal: {e}")

        logger.info(f"[The Selby] Total: {len(units)} units")
        return units

    def _parse_api(self, data: dict) -> list[UnitData]:
        raw_units  = data.get("units", [])
        floorplans = {fp["title"]: fp for fp in data.get("floorplans", [])}
        units = []

        for item in raw_units:
            try:
                unit_num = str(item.get("unit_code", "")).strip()
                fp_code  = item.get("unit_type_code", "")

                # Map fp_code → floor plan title
                fp_name = None
                for title, fp in floorplans.items():
                    if fp_code in fp.get("unit_type_codes", []):
                        fp_name = title
                        break
                if not fp_name and fp_code:
                    m = re.search(r"_([a-zA-Z]\d+[a-zA-Z]?)$", fp_code)
                    fp_name = m.group(1).upper() if m else fp_code

                beds = item.get("beds", -1)
                unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds, "Unknown")

                try:
                    bathrooms = float(item.get("baths", "") or 0) or None
                except (ValueError, TypeError):
                    bathrooms = None

                sqft  = int(item["sqft"])  if item.get("sqft")  else None
                floor = int(item["floor"]) if item.get("floor") else None

                min_rent = item.get("min_rent")
                max_rent = item.get("max_rent")
                rent     = float(min_rent) if min_rent else None
                rent_max = float(max_rent) if max_rent else None

                avail_obj  = item.get("availability", {})
                avail_date = avail_obj.get("date")
                if avail_date:
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(avail_date, "%Y-%m-%d")
                        avail_str = dt.strftime("%b %-d, %Y")
                    except Exception:
                        avail_str = avail_date
                else:
                    avail_str = avail_obj.get("display", "Available")

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
                    incentives=None,
                    source_url=PAGE_URL,
                ))
                logger.debug(f"[The Selby] ✓ #{unit_num} | {unit_type} | {fp_name} | "
                             f"Floor {floor} | {sqft}sqft | ${rent} | {avail_str}")

            except Exception as e:
                logger.debug(f"[The Selby] Unit parse: {e}")

        logger.info(f"[The Selby] Parsed {len(units)} of {len(raw_units)} units")
        return units
