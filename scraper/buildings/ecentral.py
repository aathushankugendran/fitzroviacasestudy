"""
eCentral — 15 Roehampton Avenue
Website: ecentralliving.com/rental-suites

Confirmed page structure (inspected live via Chrome):
  Table sections with class "floorplan-section bedroom-N":
    - "1 Bedroom Suites" section (class: bedroom-1)
    - "2 Bedroom Suites" section (class: bedroom-2)
    - "Townhomes Suites" section (class: bedroom-5)

  Each section has a table (.row.align-items-end.no-gutters) with rows:
    Suite Name | Bedroom | Bath | Size | Starting At | Availability

  Example row:
    "The Connected | 1 | 1 | 509 SQ.FT. | $2150 | 13/05/2026"
    "The Hub III - Townhome | 2 | 2 | 1,120 SQ.FT. | $3691 | Available Now"

  Dates are formatted DD/MM/YYYY.
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

PAGE_URL = "https://www.ecentralliving.com/rental-suites"


class ECentralScraper(BaseScraper):
    building_name = "eCentral"
    building_address = "15 Roehampton Avenue, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(8_000)
        units = []

        try:
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(3000)

            # Get all suite rows from each floorplan section
            sections_data = await page.evaluate("""
                () => {
                    const results = [];
                    // Each bedroom section has class like "floorplan-section bedroom-1"
                    const sections = document.querySelectorAll('[class*="floorplan-section"]');

                    for (const section of sections) {
                        const cls = section.className;
                        // Determine section type from class or heading
                        const heading = section.querySelector('h2, h3, h4, .section-title');
                        const sectionTitle = heading ? heading.innerText.trim() : cls;

                        // Get the table rows container
                        const tableRow = section.querySelector('.row.align-items-end.no-gutters');
                        if (!tableRow) continue;

                        const text = tableRow.innerText.trim();
                        results.push({sectionTitle, text, cls});
                    }
                    return results;
                }
            """)

            logger.info(f"[eCentral] Found {len(sections_data)} floorplan sections")

            for section in sections_data:
                title = section.get("sectionTitle", "")
                text = section.get("text", "")
                batch = self._parse_section(title, text)
                units.extend(batch)
                logger.info(f"[eCentral] Section '{title}': {len(batch)} units")

        except Exception as e:
            logger.error(f"[eCentral] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[eCentral] Total: {len(units)} units")
        return units

    def _parse_section(self, section_title: str, text: str) -> list[UnitData]:
        """
        Parse a suite table section.
        Text format (newline separated):
          Suite Name\nBedroom\nBath\nSize\nStarting At\nAvailability\n
          The Connected\n1\n1\n509 SQ.FT.\n$2150\n13/05/2026\n
          ...
        """
        units = []
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Skip header row
        header_done = False
        i = 0
        while i < len(lines):
            # Detect header
            if lines[i].lower() in ("suite name", "bedroom", "bath", "size", "starting at", "availability"):
                # Skip all header fields
                while i < len(lines) and lines[i].lower() in (
                    "suite name", "bedroom", "bath", "size", "starting at", "availability"
                ):
                    i += 1
                header_done = True
                continue

            # Each unit takes 6 fields: name, beds, baths, size, price, availability
            if i + 5 < len(lines):
                try:
                    name_raw    = lines[i]
                    beds_raw    = lines[i+1]
                    baths_raw   = lines[i+2]
                    size_raw    = lines[i+3]
                    price_raw   = lines[i+4]
                    avail_raw   = lines[i+5]

                    # Validate: beds should be a digit
                    if not re.match(r'^\d+$', beds_raw):
                        i += 1
                        continue

                    # Parse bedrooms
                    beds = int(beds_raw)
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

                    # Bathrooms
                    try:
                        bathrooms = float(baths_raw)
                    except (ValueError, TypeError):
                        bathrooms = None

                    # Sqft: "509 SQ.FT." or "1,120 SQ.FT."
                    sqft_m = re.search(r"([\d,]+)\s*SQ", size_raw, re.IGNORECASE)
                    sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None

                    # Rent: "$2150"
                    rent_m = re.search(r"\$([\d,]+)", price_raw)
                    rent = float(rent_m.group(1).replace(",", "")) if rent_m else None

                    # Availability: "13/05/2026" → "May 13, 2026" or "Available Now"
                    avail_str = self._parse_avail(avail_raw)

                    if rent and rent > 500:
                        units.append(UnitData(
                            unit_type=unit_type,
                            bedrooms=beds,
                            bathrooms=bathrooms,
                            floor_plan_name=name_raw,
                            sq_ft=sqft,
                            monthly_rent=rent,
                            available_date=avail_str,
                            incentives=None,
                            source_url=PAGE_URL,
                        ))
                        logger.debug(
                            f"[eCentral] ✓ {name_raw} | {unit_type} | "
                            f"{sqft}sqft | ${rent} | {bathrooms}bath | {avail_str}"
                        )
                    i += 6
                except Exception as e:
                    logger.debug(f"[eCentral] Row parse: {e}")
                    i += 1
            else:
                i += 1

        return units

    def _parse_avail(self, raw: str) -> str:
        """Convert DD/MM/YYYY to Month Day, Year or return as-is."""
        raw = raw.strip()
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
        if m:
            try:
                from datetime import datetime
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(year, month, day)
                return dt.strftime("%b %-d, %Y")
            except Exception:
                return raw
        return raw if raw else "Available Now"