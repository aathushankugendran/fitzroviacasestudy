"""
E18HTEEN — 18 Erskine Avenue
Website: myrental.ca/apartments-for-rent/18-erskine-ave

CONFIRMED ISSUES (Apr 28 2026):
- SVG icons block card.innerText → must use card.textContent
- Rent format: "$2195 / MO" or "FROM $2195 / MO"
- 2-bed cards are NOT in DOM on page load — only appear after clicking their filter
- Fixed timeout (1200ms) insufficient on Railway → use wait_for_selector instead
- "Show All" filter only shows 1-bed units — must cycle all 4 filters

8 units currently:
  Addison, Abbington, Elgin (1-Bed)
  Grammercy (1-Bed+Den)
  Newbury, Bedford, Bennington (2-Bed)
  Chaplin (2-Bed+Den)
"""

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
            # 2-bed cards are NOT in the DOM until their filter is clicked
            for fv in FILTER_VALUES:
                # Click the filter label
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

                # Wait for cards to appear in DOM — more reliable than fixed timeout
                try:
                    await page.wait_for_selector('.unit-group-card', timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(1000)

                # Collect cards using textContent (innerText is empty due to SVG icons)
                cards = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('.unit-group-card')).map(card => {
                        const name = card.querySelector('h3')?.textContent?.trim() || '';
                        const text = card.textContent?.replace(/\\s+/g, ' ').trim() || '';
                        const rate = text.match(/\\$([\\d,]+)\\s*\\/\\s*MO/i)?.[1]?.replace(/,/g,'') ||
                                     text.match(/FROM\\s+\\$([\\d,]+)/i)?.[1]?.replace(/,/g,'');
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
                    beds  = schema.get("beds", -1)
                    baths = schema.get("baths")
                    sqft  = schema.get("sqft")

                    # Fallback beds from filter value
                    if beds == -1:
                        bed_val = fv.split("--")[0]
                        beds = int(bed_val) if bed_val.isdigit() else 1

                    unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")
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
