"""
E18HTEEN — 18 Erskine Avenue
Website: myrental.ca/apartments-for-rent/18-erskine-ave

CONFIRMED IN CHROME (Apr 28 2026):
- All unit-group-cards are in the DOM at load time (no API calls)
- Filter clicks show/hide cards — but innerText is EMPTY on cards because SVG icons block it
- Must use card.textContent NOT card.innerText
- Rent format is "$3395 / MO" NOT "FROM $3,395"
- Schema JSON-LD has sqft + baths for each unit

7 units confirmed:
  Addison     1Bed/1Bath/460sqft/$2,195
  Abbington   1Bed/1Bath/479sqft/$2,250
  Elgin       1Bed/1Bath/530sqft/$2,365
  Grammercy   1Bed+Den/1Bath/612sqft/$2,500
  Bedford     2Bed/2Bath/794sqft/$3,250
  Bennington  2Bed/2Bath/804sqft/$3,295
  Chaplin     2Bed+Den/2Bath/847sqft/$3,395
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL = "https://www.myrental.ca/apartments-for-rent/18-erskine-ave"


class E18HTEENScraper(BaseScraper):
    building_name = "E18HTEEN"
    building_address = "18 Erskine Avenue, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(20_000)
        units = []
        seen = set()

        try:
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(2000)

            # Step 1: Get sqft + baths + beds from JSON-LD schema
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
                                        sqft:  a.floorSize?.value,
                                        baths: a.numberOfBathroomsTotal,
                                        beds:  a.numberOfBedrooms
                                    };
                                }
                            });
                        } catch(e) {}
                    });
                    return map;
                }
            """)
            logger.info(f"[E18HTEEN] JSON-LD: {len(schema_map)} entries")

            # Step 2: Click each filter and collect cards
            # CRITICAL: use textContent NOT innerText — innerText is empty due to SVG icons
            # CRITICAL: rent format is "$3395 / MO" not "FROM $3,395"
            filter_values = ["1--false", "1--true", "2--false", "2--true"]

            for fv in filter_values:
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

                await page.wait_for_timeout(1200)

                # Use textContent — works even when innerText is empty due to SVGs
                cards = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('.unit-group-card')).map(card => {
                        const name = card.querySelector('h3')?.textContent?.trim() || '';
                        const text = card.textContent?.replace(/\\s+/g, ' ').trim() || '';
                        // Match "$3395 / MO" format
                        const rate = text.match(/\\$([\\d,]+)\\s*\\/\\s*MO/i)?.[1]?.replace(',','') ||
                                     text.match(/FROM\\s+\\$([\\d,]+)/i)?.[1]?.replace(',','');
                        return {name, rate};
                    }).filter(c => c.name && c.rate)
                """)

                logger.info(f"[E18HTEEN] Filter '{fv}': {len(cards)} cards — {[c['name'] for c in cards]}")

                for card in cards:
                    name = card["name"]
                    if name in seen:
                        continue
                    seen.add(name)

                    schema = schema_map.get(name.lower().strip(), {})
                    beds      = schema.get("beds", -1)
                    baths     = schema.get("baths")
                    sqft      = schema.get("sqft")

                    if beds == -1:
                        bed_val = fv.split("--")[0]
                        beds = int(bed_val) if bed_val.isdigit() else 1

                    unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds, "Unknown")
                    bathrooms = float(baths) if baths else (2.0 if beds >= 2 else 1.0)

                    try:
                        rent = float(str(card["rate"]).replace(",",""))
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
                    logger.debug(f"[E18HTEEN] ✓ {name} | {unit_type} | {sqft}sqft | ${rent}")

        except Exception as e:
            logger.error(f"[E18HTEEN] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[E18HTEEN] Total: {len(units)} suites")
        return units
