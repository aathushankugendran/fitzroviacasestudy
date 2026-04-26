"""
Akoya Living — 55 Broadway Avenue
Website: akoyaliving.ca/suites

API: https://website-gateway.rentsync.com/v1/t2r_akoya/unit-table-builder
     ?where=propertyId~in:303333,type~in:columns,showUnavailableUnits~in:false

Response structure (confirmed live Apr 26 2026):
  data → object (NOT array) with keys: property, units, columns, filters, settings
  data.units[] → array of unit objects

Unit fields: typeName, bed, bath, den, sqFt, rate, available (1=yes, 0=no, -1=waitlist)
"""

import json
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL = "https://www.akoyaliving.ca/suites"
API_URL  = ("https://website-gateway.rentsync.com/v1/t2r_akoya/unit-table-builder"
            "?where=propertyId~in:303333,type~in:columns,showUnavailableUnits~in:false")


class AkoyaScraper(BaseScraper):
    building_name = "Akoya Living"
    building_address = "55 Broadway Avenue, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(10_000)
        units = []

        try:
            # Visit page first to establish session/cookies
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(2000)

            # Fetch API using page context (inherits cookies/headers)
            raw_units = await page.evaluate(f"""
                async () => {{
                    const r = await fetch('{API_URL}', {{credentials: 'include'}});
                    const d = await r.json();
                    // data is an object with a units[] array
                    return d?.data?.units || d?.data?.[0]?.units || [];
                }}
            """)

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

                    unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(bed,"Unknown")
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
        finally:
            await page.close()

        logger.info(f"[Akoya] Total: {len(units)} units")
        return units