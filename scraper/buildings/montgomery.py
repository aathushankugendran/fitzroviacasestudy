"""
The Montgomery — 2388 Yonge Street
Website: themontgomery.ca/floorplans (RentCafe + Cloudflare Turnstile)

CONFIRMED via Chrome (Apr 26 2026):
- Cloudflare Turnstile blocks headless Playwright navigation
- BUT: fetching via page.evaluate (from within the browser) with credentials works
- The Cloudflare cookies set on page load allow subsequent fetches to succeed

Strategy:
1. Navigate to /floorplans once (triggers Cloudflare, sets cookies in browser)
2. Use page.evaluate(fetch) to get all floor plan URLs from /floorplans HTML
3. Use page.evaluate(fetch) to get each /floorplans/X page HTML
4. Parse card-body divs for apartment data
"""

import re
from loguru import logger
from scraper.base import BaseScraper, UnitData

BASE_URL       = "https://www.themontgomery.ca"
FLOORPLANS_URL = "https://www.themontgomery.ca/floorplans"


class MontgomeryScraper(BaseScraper):
    building_name = "The Montgomery"
    building_address = "2388 Yonge Street, Toronto, ON"
    url = FLOORPLANS_URL

    async def _start_browser(self, playwright):
        """Stealth browser to pass Cloudflare Turnstile."""
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-CA",
        )
        await self._context.add_init_script("""
            delete Object.getPrototypeOf(navigator).webdriver;
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        """)

    async def _do_scrape(self) -> list[UnitData]:
        page = await self._new_page()
        page.set_default_timeout(20_000)
        units = []

        try:
            # Step 1: Navigate to /floorplans — this passes Cloudflare and sets cookies
            logger.info("[The Montgomery] Loading main page to pass Cloudflare...")
            await page.goto(FLOORPLANS_URL, wait_until="networkidle", timeout=self.NAV_TIMEOUT)
            await page.wait_for_timeout(3000)

            # Verify we passed Cloudflare
            title = await page.title()
            logger.info(f"[The Montgomery] Page title: {title}")
            if "security" in title.lower() or "verify" in title.lower():
                logger.error("[The Montgomery] Still on Cloudflare challenge page")
                return []

            # Step 2: Read floor plan URLs directly from the already-loaded DOM
            fp_urls = await page.evaluate("""
                () => {
                    const seen = new Set();
                    const urls = [];
                    for (const a of document.querySelectorAll('a[href*="/floorplans/"]')) {
                        const href = a.getAttribute('href') || '';
                        const full = href.startsWith('http') ? href : 'https://www.themontgomery.ca' + href;
                        if (full.includes('themontgomery.ca/floorplans/')
                            && !full.includes('#')
                            && !full.includes('javascript')
                            && !seen.has(full)) {
                            seen.add(full);
                            urls.push(full);
                        }
                    }
                    return urls;
                }
            """)

            logger.info(f"[The Montgomery] Found {len(fp_urls)} floor plan pages: "
                        f"{[u.split('/')[-1] for u in fp_urls]}")

            # Step 3: Fetch each floor plan page HTML using page.evaluate (with cookies)
            for fp_url in fp_urls:
                try:
                    page_data = await page.evaluate(f"""
                        async () => {{
                            const r = await fetch('{fp_url}', {{credentials: 'include'}});
                            const html = await r.text();
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(html, 'text/html');

                            // Floor plan info — use textContent (innerText undefined in DOMParser docs)
                            const h1 = doc.querySelector('h1');
                            const name = h1?.textContent?.trim() || '';

                            const text = doc.body?.textContent || '';

                            // Apartment cards — class_= partial match: "card-body text-center"
                            const allCards = Array.from(doc.querySelectorAll('div[class*="card-body"]'));
                            const aptCards = allCards.filter(c => c.textContent.includes('Apartment:'));

                            return {{
                                name,
                                bodyText: text.slice(0, 2000),
                                aptCards: aptCards.map(c => c.textContent.trim().replace(/\s+/g,' '))
                            }};
                        }}
                    """)

                    fp_name   = page_data.get("name", fp_url.split("/")[-1])
                    body_text = page_data.get("bodyText", "")
                    apt_cards = page_data.get("aptCards", [])

                    # Parse beds/baths/sqft from body text
                    bed_m  = re.search(r"(\d+)\s*Bedroom",  body_text, re.IGNORECASE)
                    bath_m = re.search(r"(\d+(?:\.\d)?)\s*Bathroom", body_text, re.IGNORECASE)
                    sqft_m = (re.search(r"Up to ([\d,]+)\s*Sq", body_text, re.IGNORECASE) or
                              re.search(r"([\d,]+)\s*Sq\.\s*Ft", body_text, re.IGNORECASE))

                    beds      = int(bed_m.group(1))                  if bed_m  else -1
                    bathrooms = float(bath_m.group(1))               if bath_m else None
                    sqft      = int(sqft_m.group(1).replace(",","")) if sqft_m else None
                    unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")

                    logger.info(f"[The Montgomery] {fp_name} | {unit_type} | {sqft}sqft | "
                                f"{len(apt_cards)} apt cards")

                    seen_units = set()
                    for card_text in apt_cards:
                        apt_m  = re.search(r"Apartment:\s*#\s*(\w+)", card_text, re.IGNORECASE)
                        date_m = re.search(r"Date Available:\s*([\d/]+)", card_text, re.IGNORECASE)
                        rent_m = re.search(r"Starting at:\s*\$([\d,]+)/Month", card_text, re.IGNORECASE)

                        if not apt_m:
                            continue
                        unit_num = apt_m.group(1).strip()
                        if unit_num in seen_units:
                            continue
                        seen_units.add(unit_num)

                        avail_raw = date_m.group(1) if date_m else None
                        try:
                            rent = float(rent_m.group(1).replace(",","")) if rent_m else None
                        except Exception:
                            rent = None

                        if not rent or rent < 500:
                            continue

                        avail_str = self._parse_date(avail_raw) if avail_raw else "Available Now"
                        units.append(UnitData(
                            unit_number=unit_num,
                            unit_type=unit_type,
                            bedrooms=beds,
                            bathrooms=bathrooms,
                            floor_plan_name=fp_name,
                            sq_ft=sqft,
                            monthly_rent=rent,
                            available_date=avail_str,
                            incentives=None,
                            source_url=fp_url,
                        ))
                        logger.debug(f"[The Montgomery] ✓ #{unit_num} | {fp_name} | "
                                     f"{unit_type} | ${rent} | {avail_str}")

                except Exception as e:
                    logger.debug(f"[The Montgomery] Error on {fp_url}: {e}")

        except Exception as e:
            logger.error(f"[The Montgomery] Fatal: {e}")
        finally:
            await page.close()

        logger.info(f"[The Montgomery] Total: {len(units)} apartments")
        return units

    def _parse_date(self, raw: str) -> str:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(raw).strip())
        if m:
            try:
                from datetime import datetime
                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return dt.strftime("%b %-d, %Y")
            except Exception:
                return raw
        return raw