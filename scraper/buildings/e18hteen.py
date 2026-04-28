"""
E18HTEEN — 18 Erskine Avenue
Uses Rentsync unit-table-builder API directly (propertyId: 33874, siteKey: kg_rebuild)
No Playwright needed — same API as Akoya Living.
Confirmed: returns all 9 units with prices via direct httpx call.
"""

import httpx
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL = "https://www.myrental.ca/apartments-for-rent/18-erskine-ave"
API_URL  = ("https://website-gateway.rentsync.com/v1/kg_rebuild/unit-table-builder"
            "?where=propertyId~in:33874,type~in:columns,showUnavailableUnits~in:false")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.myrental.ca/",
    "Origin": "https://www.myrental.ca",
}


class E18HTEENScraper(BaseScraper):
    building_name = "E18HTEEN"
    building_address = "18 Erskine Avenue, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        units = []

        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
                resp = await client.get(API_URL)
                logger.info(f"[E18HTEEN] API status: {resp.status_code}")

                if resp.status_code != 200:
                    logger.error(f"[E18HTEEN] API blocked: {resp.status_code}")
                    return []

                data = resp.json()
                raw_units = (data.get("data") or {}).get("units") or []
                logger.info(f"[E18HTEEN] API returned {len(raw_units)} units")

                for item in raw_units:
                    try:
                        if item.get("available", 0) == 0:
                            continue

                        name  = (item.get("typeName") or "").strip()
                        beds  = int(item.get("bed", 1))
                        baths = item.get("bath")
                        sqft  = item.get("sqFt", "")
                        rate  = item.get("rate", "")
                        den   = item.get("den", "no") == "yes"

                        unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")
                        bathrooms = float(baths) if baths else (2.0 if beds >= 2 else 1.0)

                        try:
                            rent = float(str(rate).replace(",",""))
                        except Exception:
                            continue
                        if rent < 500:
                            continue

                        try:
                            sqft_val = int(str(sqft).replace(",","")) if sqft else None
                        except Exception:
                            sqft_val = None

                        units.append(UnitData(
                            unit_type=unit_type,
                            bedrooms=beds,
                            bathrooms=bathrooms,
                            floor_plan_name=name,
                            sq_ft=sqft_val,
                            monthly_rent=rent,
                            available_date="Available Now",
                            incentives=None,
                            source_url=PAGE_URL,
                        ))
                        logger.debug(f"[E18HTEEN] ✓ {name} | {unit_type} | {sqft_val}sqft | ${rent}")

                    except Exception as e:
                        logger.debug(f"[E18HTEEN] Unit parse error: {e}")

        except Exception as e:
            logger.error(f"[E18HTEEN] Fatal: {e}")

        logger.info(f"[E18HTEEN] Total: {len(units)} suites")
        return units
