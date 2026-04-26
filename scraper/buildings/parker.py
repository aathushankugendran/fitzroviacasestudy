"""
Parker — 200 Redpath Avenue
Website: parkerlife.ca/floorplans

Confirmed page structure (from live screenshots):
  - Floor plan cards: Primrose, Holland, Battersea, etc.
  - Each card has "CHECK AVAILABILITY" button at bottom
  - Clicking opens modal with:
      h1/h2: "Holland - 1 Bedroom, 1 Bathroom"
      Table: Suite# | Floor | Sq.Ft. | Rent | Availability | Action

All bedroom/bathroom info is in the modal title — no need for detail pages.
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

INCENTIVES = "Up to 2 months free + complimentary Wi-Fi"


class ParkerScraper(BaseScraper):
    building_name = "Parker"
    building_address = "200 Redpath Avenue, Toronto, ON"
    url = "https://www.parkerlife.ca/floorplans"

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(8_000)
        units = []

        try:
            await page.goto(self.url, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(3000)

            page_text = await page.inner_text("body")
            incentives = INCENTIVES  # hardcoded — page text extraction unreliable for Parker

            # Find all CHECK AVAILABILITY buttons
            avail_buttons = await page.query_selector_all(
                "a, button"
            )
            check_avail_buttons = []
            for btn in avail_buttons:
                try:
                    txt = (await btn.inner_text()).strip().upper()
                    if "CHECK AVAILABILITY" in txt or "AVAILABILITY" in txt:
                        check_avail_buttons.append(btn)
                except Exception:
                    pass

            logger.info(f"[Parker] Found {len(check_avail_buttons)} CHECK AVAILABILITY buttons")

            for i, btn in enumerate(check_avail_buttons):
                try:
                    # JS click — no visibility timeout
                    await page.evaluate("el => el.click()", btn)
                    await page.wait_for_timeout(2000)

                    # Extract everything from the modal via JS
                    result = await page.evaluate("""
                        () => {
                            // Find modal — look for any dialog/overlay that appeared
                            // and contains a table (the key indicator)
                            let modal = null;

                            // Strategy 1: standard modal selectors
                            const modalSels = [
                                'dialog[open]',
                                '[class*="modal"]:not([hidden])',
                                '[role="dialog"]',
                                '[class*="popup"]',
                                '[class*="overlay"]:not([class*="nav"])',
                                '[class*="Popup"]',
                                '[class*="Modal"]',
                            ];
                            for (const s of modalSels) {
                                const els = document.querySelectorAll(s);
                                for (const el of els) {
                                    if (el.querySelector('table') && el.offsetParent !== null) {
                                        modal = el;
                                        break;
                                    }
                                }
                                if (modal) break;
                            }

                            // Strategy 2: find any visible element with a table
                            // that contains rent data
                            if (!modal) {
                                const tables = document.querySelectorAll('table');
                                for (const t of tables) {
                                    const txt = t.innerText;
                                    if (txt.includes('$') && txt.includes('Floor')) {
                                        // Walk up to find the container
                                        modal = t.closest('[class*="modal"], [class*="popup"], [class*="overlay"], dialog, section, div[style*="position: fixed"], div[style*="z-index"]') || t.parentElement;
                                        break;
                                    }
                                }
                            }

                            if (!modal) return null;

                            // Extract the title — look for heading with "Bedroom" or "Studio" or "Bathroom"
                            let title = '';

                            // First try: headings WITHIN the modal that contain bedroom info
                            const headings = modal.querySelectorAll('h1, h2, h3, h4');
                            for (const h of headings) {
                                const t = h.innerText.trim();
                                if (t.match(/bedroom|studio|bachelor|bathroom/i) && t.length > 3) {
                                    title = t;
                                    break;
                                }
                            }

                            // Second try: any text node with bedroom/bathroom pattern
                            if (!title) {
                                const walker = document.createTreeWalker(modal, NodeFilter.SHOW_TEXT);
                                let node;
                                while (node = walker.nextNode()) {
                                    const t = node.textContent.trim();
                                    if (t.match(/(studio|bachelor|[0-9]+ bedroom|[0-9]+ bathroom)/i) && t.length > 5) {
                                        title = t;
                                        break;
                                    }
                                }
                            }

                            // Get table rows
                            const rows = [];
                            const trs = modal.querySelectorAll('table tr');
                            for (const tr of trs) {
                                const cells = Array.from(tr.querySelectorAll('td, th'));
                                if (cells.length >= 4) {
                                    rows.push(cells.map(c => c.innerText.trim()));
                                }
                            }

                            return { title, rows, modalFound: !!modal };
                        }
                    """)

                    if not result:
                        logger.debug(f"[Parker] No modal/table for button {i}")
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(400)
                        continue

                    fp_title = result.get("title", "").strip()
                    rows = result.get("rows", [])

                    logger.info(f"[Parker] Card {i}: title='{fp_title}' → {len(rows)} rows")

                    # Parse bedrooms and bathrooms from title
                    # e.g. "Holland - 1 Bedroom, 1 Bathroom" or "Primrose - Studio, 1 Bathroom"
                    bedrooms = -1
                    bathrooms = None

                    if fp_title:
                        title_lower = fp_title.lower()
                        if re.search(r'studio|bachelor', title_lower):
                            bedrooms = 0
                        else:
                            m = re.search(r'(\d+)\s*bed', title_lower)
                            if m:
                                bedrooms = int(m.group(1))

                        bm = re.search(r'(\d+(?:\.\d)?)\s*bath', title_lower)
                        if bm:
                            bathrooms = float(bm.group(1))

                    # Map bedrooms count → unit_type label
                    type_map = {0: "Bachelor", 1: "1-Bed", 2: "2-Bed", 3: "3-Bed"}
                    unit_type = type_map.get(bedrooms, "Unknown")

                    # Parse the table rows
                    for row in rows:
                        first = row[0].lower() if row else ""
                        # Skip header rows
                        if first in ("suite#", "suite", "unit", "#", "floor", ""):
                            continue

                        try:
                            # Columns: Suite# | Floor | Sq.Ft. | Rent | Availability | Action
                            suite_num  = row[0] if len(row) > 0 else None
                            floor_raw  = row[1] if len(row) > 1 else None
                            sqft_raw   = row[2] if len(row) > 2 else None
                            rent_raw   = row[3] if len(row) > 3 else None
                            avail_raw  = row[4] if len(row) > 4 else None

                            rent      = self.parse_rent(rent_raw or "")
                            sqft      = self.parse_sqft(sqft_raw or "")
                            floor_num = int(floor_raw) if floor_raw and floor_raw.isdigit() else None

                            # Clean availability
                            avail = avail_raw
                            if avail and avail.lower() in ("action", "more details", "apply", "book", ""):
                                avail = None

                            if rent:
                                units.append(UnitData(
                                    unit_number=suite_num,
                                    unit_type=unit_type,
                                    bedrooms=bedrooms,
                                    bathrooms=bathrooms,
                                    floor_plan_name=fp_title or None,
                                    monthly_rent=rent,
                                    sq_ft=sqft,
                                    floor=floor_num,
                                    available_date=avail,
                                    incentives=incentives,
                                    source_url=self.url,
                                ))
                                logger.debug(
                                    f"[Parker] ✓ Suite {suite_num} | {unit_type} | "
                                    f"Floor {floor_num} | {sqft}sqft | "
                                    f"${rent} | {avail} | {bathrooms} bath"
                                )
                        except Exception as e:
                            logger.debug(f"[Parker] row: {e}")

                    # Close modal
                    closed = await page.evaluate("""
                        () => {
                            const sels = [
                                '[class*="close"]', '[aria-label*="close" i]',
                                '.modal-close', '[class*="dismiss"]',
                                'button[class*="modal"]',
                            ];
                            for (const s of sels) {
                                const el = document.querySelector(s);
                                if (el) { el.click(); return true; }
                            }
                            return false;
                        }
                    """)
                    if not closed:
                        await page.keyboard.press("Escape")
                    await page.wait_for_timeout(700)

                except Exception as e:
                    logger.debug(f"[Parker] button {i} error: {e}")
                    try:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(400)
                    except Exception:
                        pass

            if not units:
                logger.warning("[Parker] Modal approach empty — text fallback")
                units = self._text_fallback(page_text, incentives)

        except Exception as e:
            logger.error(f"[Parker] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[Parker] Total: {len(units)} units")
        return units

    def _text_fallback(self, text: str, incentives: str) -> list[UnitData]:
        units, seen = [], set()
        for m in re.finditer(
            r"(studio|bachelor|1[\s-]bed(?:room)?|2[\s-]bed(?:room)?|3[\s-]bed(?:room)?)"
            r"[^$\n]{0,120}\$([\d,]+)",
            text, re.IGNORECASE,
        ):
            rent_val = float(m.group(2).replace(",", ""))
            if rent_val in seen or not (1000 < rent_val < 10000):
                continue
            seen.add(rent_val)
            unit_type, bedrooms = self.normalize_unit_type(m.group(1))
            units.append(UnitData(
                unit_type=unit_type, bedrooms=bedrooms,
                monthly_rent=rent_val, incentives=incentives,
                source_url=self.url,
            ))
        return units