"""
The Whitney on Redpath — 65 Redpath Avenue
Scrapes from two pages:
  1. https://www.thewhitneyonredpath.com/apartments/
  2. https://www.thewhitneyonredpath.com/skyline-view-collection/

Confirmed card format (Elementor-based WordPress site):
  "CINNAMON\n\nChic Retreat\n\nSTUDIO / 1 BATH\n\n325 SF\n\nFROM $2,100\n\nLEARN MORE"
  "TEAL\n\nIndoor-Outdoor Living\n\n1 BED / 1 BATH\n\n524 SF\n\nFROM $2,550\n\nLEARN MORE"
  "CERISE\n\nCorner Retreat\n\n2 BED / 2 BATH\n\n788 SF\n\nFROM $3,445\n\nLEARN MORE"

Fields: Floor Plan Name | Tagline | Bed/Bath type | SF | Price
No individual unit numbers — floor plan level pricing only.
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

URLS = [
    "https://www.thewhitneyonredpath.com/apartments/",
    "https://www.thewhitneyonredpath.com/skyline-view-collection/",
]


class WhitneyScraper(BaseScraper):
    building_name = "The Whitney"
    building_address = "65 Redpath Avenue, Toronto, ON"
    url = URLS[0]

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(10_000)
        units = []
        seen_plans = set()

        try:
            for url in URLS:
                await page.goto(url, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
                await page.wait_for_timeout(2000)

                cards = await page.evaluate("""
                    () => {
                        const seen = new Set();
                        const results = [];
                        const els = document.querySelectorAll('.elementor-element');
                        for (const el of els) {
                            const t = el.innerText || '';
                            if (
                                t.includes('$') &&
                                (t.includes('BED') || t.includes('STUDIO') || t.includes('BATH')) &&
                                t.length > 30 && t.length < 400
                            ) {
                                const key = t.trim().slice(0, 50);
                                if (!seen.has(key)) {
                                    seen.add(key);
                                    results.push(t.trim());
                                }
                            }
                        }
                        return results;
                    }
                """)

                logger.info(f"[The Whitney] {url.split('/')[-2]}: {len(cards)} raw cards")

                for card in cards:
                    unit = self._parse_card(card, url, seen_plans)
                    if unit:
                        units.append(unit)

        except Exception as e:
            logger.error(f"[The Whitney] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Whitney] Total: {len(units)} floor plans")
        return units

    def _parse_card(self, text: str, source_url: str, seen_plans: set) -> UnitData | None:
        """
        Parse a Whitney apartment card.
        Format: NAME\n\nTagline\n\nTYPE / N BATH\n\nNNN SF\n\nFROM $X,XXX\n\nLEARN MORE
        Also handles compact: NAMETaglineTYPE / N BATHSF NNN SFRENTFROM $X,XXX
        """
        try:
            # Skip header/table rows
            if text.startswith("FLOOR PLAN") or text.startswith("APARTMENTS"):
                return None
            if text.startswith("BED/BATHS") or "LEARN MORE" not in text:
                return None

            # Clean text — collapse whitespace variants
            lines = [l.strip() for l in re.split(r'\n+', text) if l.strip()]
            lines = [l for l in lines if l not in ("LEARN MORE", "FLOOR PLAN", "BED/BATHS", "SF", "RENT", "APARTMENTS")]

            if not lines:
                return None

            # Floor plan name = first line (all caps color name)
            fp_name = lines[0]

            # Deduplicate by floor plan name
            if fp_name in seen_plans:
                return None
            seen_plans.add(fp_name)

            # Join remaining for regex parsing
            full = " ".join(lines)

            # Bed/bath type: "STUDIO / 1 BATH", "1 BED / 1 BATH", "2 BED + DEN / 2 BATH"
            type_m = re.search(
                r"(STUDIO|\d+\s*BED(?:\s*\+\s*DEN)?)\s*/\s*(\d+(?:\.\d)?)\s*BATH",
                full, re.IGNORECASE
            )
            if not type_m:
                return None

            raw_type = type_m.group(1).strip().upper()
            bath_raw = type_m.group(2)
            bathrooms = float(bath_raw)

            # Classify
            if "STUDIO" in raw_type:
                unit_type, bedrooms = "Bachelor", 0
            elif "DEN" in raw_type:
                bed_m = re.search(r"(\d+)", raw_type)
                bedrooms = int(bed_m.group(1)) if bed_m else 1
                unit_type = f"{bedrooms}-Bed"
            else:
                bed_m = re.search(r"(\d+)", raw_type)
                bedrooms = int(bed_m.group(1)) if bed_m else 1
                unit_type = f"{bedrooms}-Bed"

            # Sqft: "325 SF" or "325 SF"
            sqft_m = re.search(r"(\d[\d,]*)\s*SF", full, re.IGNORECASE)
            sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None

            # Rent: "FROM $2,100" or "$6,000"
            rent_m = re.search(r"\$\s*([\d,]+)", full)
            rent = float(rent_m.group(1).replace(",", "")) if rent_m else None

            if not rent or rent < 500:
                return None

            logger.debug(
                f"[The Whitney] ✓ {fp_name} | {unit_type} | "
                f"{sqft}sqft | ${rent} | {bathrooms}bath"
            )

            return UnitData(
                unit_type=unit_type,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                floor_plan_name=fp_name,
                sq_ft=sqft,
                monthly_rent=rent,
                available_date="Available Now",
                incentives=None,
                source_url=source_url,
            )

        except Exception as e:
            logger.debug(f"[The Whitney] Card parse: {e}")
            return None