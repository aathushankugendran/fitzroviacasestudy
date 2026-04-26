"""
E18HTEEN — 18 Erskine Avenue
Website: myrental.ca/apartments-for-rent/18-erskine-ave

CONFIRMED via Chrome (Apr 26 2026):
- Filter: must click PARENT LABEL (.input-radio__label:has(input[data-value="X"]))
  NOT the input itself — clicking the input doesn't update the DOM
- Filter values: "1--false", "1--true", "2--false", "2--true"
- Cards: .unit-group-card with h3 innerHTML for name
- All 7 suites confirmed: Addison, Abbington, Elgin, Grammercy, Bedford, Bennington, Chaplin
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL      = "https://www.myrental.ca/apartments-for-rent/18-erskine-ave"
FILTER_VALUES = ["1--false", "1--true", "2--false", "2--true"]


class E18HTEENScraper(BaseScraper):
    building_name = "E18HTEEN"
    building_address = "18 Erskine Avenue, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(12_000)
        units = []
        seen = set()

        try:
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(2000)

            # Step 1: Get sqft + baths from JSON-LD schema
            schema_map = await page.evaluate("""
                () => {
                    const map = {};
                    document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                        try {
                            const data = JSON.parse(s.innerText);
                            (data.containsPlace || []).forEach(a => {
                                if (a['@type'] === 'Apartment') {
                                    const key = a.name.replace(/\\s*\\(.*?\\)/g, '').trim().toLowerCase();
                                    map[key] = {
                                        sqft: a.floorSize?.value,
                                        baths: a.numberOfBathroomsTotal,
                                        beds: a.numberOfBedrooms
                                    };
                                }
                            });
                        } catch(e) {}
                    });
                    return map;
                }
            """)
            logger.info(f"[E18HTEEN] JSON-LD: {len(schema_map)} entries")

            # Step 2: Click each filter LABEL (not input) and collect cards
            for fv in FILTER_VALUES:
                # CONFIRMED: must click parent .input-radio__label using :has() selector
                clicked = await page.evaluate(f"""
                    () => {{
                        const label = document.querySelector(
                            '.input-radio__label:has(input[data-value="{fv}"])'
                        );
                        if (label) {{ label.click(); return true; }}
                        return false;
                    }}
                """)

                if not clicked:
                    logger.debug(f"[E18HTEEN] Filter '{fv}' not found")
                    continue

                await page.wait_for_timeout(1000)

                cards = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('.unit-group-card')).map(card => ({
                        name: card.querySelector('h3')?.innerHTML?.trim() || '',
                        rate: (card.innerText.match(/FROM \\$([\d,]+)/) || [])[1] || null
                    })).filter(c => c.name && c.rate)
                """)

                logger.info(f"[E18HTEEN] Filter '{fv}': {len(cards)} cards — "
                            f"{[c['name'] for c in cards]}")

                for card in cards:
                    name     = card["name"]
                    rent_raw = card["rate"]
                    if name in seen:
                        continue
                    seen.add(name)

                    schema_key = name.lower().strip()
                    schema = schema_map.get(schema_key, {})

                    beds  = schema.get("beds", -1)
                    baths = schema.get("baths")
                    sqft  = schema.get("sqft")

                    if beds == -1:
                        bed_val = fv.split("--")[0]
                        beds = int(bed_val) if bed_val.isdigit() else 1

                    unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")
                    bathrooms = float(baths) if baths else (2.0 if beds >= 2 else 1.0)

                    try:
                        rent = float(rent_raw.replace(",",""))
                    except Exception:
                        continue

                    if rent < 500:
                        continue

                    units.append(UnitData(
                        unit_type=unit_type,
                        bedrooms=beds,
                        bathrooms=bathrooms,
                        floor_plan_name=name,
                        sq_ft=int(sqft) if sqft else None,
                        monthly_rent=rent,
                        available_date="Available Now",
                        incentives=None,
                        source_url=PAGE_URL,
                    ))
                    logger.debug(f"[E18HTEEN] ✓ {name} | {unit_type} | {sqft}sqft | ${rent} | {bathrooms}bath")

        except Exception as e:
            logger.error(f"[E18HTEEN] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[E18HTEEN] Total: {len(units)} suites")
        return units