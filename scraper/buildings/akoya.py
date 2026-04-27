"""
Akoya Living — 55 Broadway Avenue
API: https://website-gateway.rentsync.com/v1/t2r_akoya/unit-table-builder
     ?where=propertyId~in:303333,type~in:columns,showUnavailableUnits~in:false

Uses httpx directly — no Playwright or page.evaluate needed.
Response: data → object with data.units[]
"""

import httpx
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL = "https://www.akoyaliving.ca/suites"
API_URL  = ("https://website-gateway.rentsync.com/v1/t2r_akoya/unit-table-builder"
            "?where=propertyId~in:303333,type~in:columns,showUnavailableUnits~in:false")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.akoyaliving.ca/",
    "Origin": "https://www.akoyaliving.ca",
}


class AkoyaScraper(BaseScraper):
    building_name = "Akoya Living"
    building_address = "55 Broadway Avenue, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        units = []

        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
                resp = await client.get(API_URL)
                logger.info(f"[Akoya] API status: {resp.status_code}")

                if resp.status_code != 200:
                    logger.error(f"[Akoya] API returned {resp.status_code}")
                    return []

                data = resp.json()
                raw_units = (data.get("data") or {}).get("units") or []
                logger.info(f"[Akoya] API returned {len(raw_units)} units")

                for item in raw_units:
                    try:
                        if item.get("available", 0) == 0:
                            continue

                        type_name = str(item.get("typeName", "")).strip()
                        bed       = int(item.get("bed", -1))
                        bath      = item.get("bath")
                        sqft_raw  = item.get("sqFt", "")
                        rate_raw  = item.get("rate", "")

                        unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(bed, "Unknown")
                        bathrooms = float(bath) if bath else None
                        sqft      = int(sqft_raw) if str(sqft_raw).isdigit() else None
                        rent      = float(rate_raw) if str(rate_raw).replace(".","").isdigit() else None

                        if not rent or rent < 500:
                            continue

                        units.append(UnitData(
                            unit_type=unit_type,
                            bedrooms=bed,
                            bathrooms=bathrooms,
                            floor_plan_name=type_name,
                            sq_ft=sqft,
                            monthly_rent=rent,
                            available_date="Available Now",
                            incentives=None,
                            source_url=PAGE_URL,
                        ))
                        logger.debug(f"[Akoya] ✓ {type_name} | {unit_type} | {sqft}sqft | ${rent} | {bathrooms}bath")

                    except Exception as e:
                        logger.debug(f"[Akoya] Unit parse: {e}")

        except Exception as e:
            logger.error(f"[Akoya] Fatal: {e}")

        logger.info(f"[Akoya] Total: {len(units)} units")
        return units
