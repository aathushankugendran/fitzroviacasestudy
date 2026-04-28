"""
The Montgomery — 2388 Yonge Street
Website: themontgomery.ca/floorplans

CONFIRMED (Chrome Apr 27 2026): Data available without cookies via plain HTTP.
Uses httpx directly — no Playwright needed.

11 units confirmed across 8 floor plans:
  Oriole, Lillian-D, Roselawn III, Anderson-D,
  Maxwell, Broadway II, Redpath IV, Oswald
"""

import re
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from scraper.base import BaseScraper, UnitData

BASE_URL       = "https://www.themontgomery.ca"
FLOORPLANS_URL = "https://www.themontgomery.ca/floorplans"

FP_URLS = [
    "https://www.themontgomery.ca/floorplans/oriole",
    "https://www.themontgomery.ca/floorplans/lillian---d",
    "https://www.themontgomery.ca/floorplans/roselawn-iii---penthouse-collection",
    "https://www.themontgomery.ca/floorplans/anderson---d",
    "https://www.themontgomery.ca/floorplans/maxwell",
    "https://www.themontgomery.ca/floorplans/broadway-ii---th",
    "https://www.themontgomery.ca/floorplans/redpath-iv",
    "https://www.themontgomery.ca/floorplans/oswald",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.themontgomery.ca/floorplans",
    "Origin": "https://www.themontgomery.ca",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}


class MontgomeryScraper(BaseScraper):
    building_name = "The Montgomery"
    building_address = "2388 Yonge Street, Toronto, ON"
    url = FLOORPLANS_URL

    async def _do_scrape(self) -> list[UnitData]:
        units = []
        seen_units = set()

        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            for fp_url in FP_URLS:
                try:
                    resp = await client.get(fp_url)
                    logger.info(f"[The Montgomery] {fp_url.split('/')[-1]}: status {resp.status_code}")

                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "lxml")

                    # Floor plan name
                    h1 = soup.find("h1")
                    fp_name = h1.get_text(strip=True) if h1 else fp_url.split("/")[-1]

                    # Beds / baths / sqft from page text
                    text = soup.get_text(separator=" ")
                    bed_m  = re.search(r"(\d+)\s*Bedroom",  text, re.IGNORECASE)
                    bath_m = re.search(r"(\d+(?:\.\d)?)\s*Bathroom", text, re.IGNORECASE)
                    sqft_m = (re.search(r"Up to ([\d,]+)\s*Sq", text, re.IGNORECASE) or
                              re.search(r"([\d,]+)\s*Sq\.\s*Ft", text, re.IGNORECASE))

                    beds      = int(bed_m.group(1))                  if bed_m  else -1
                    bathrooms = float(bath_m.group(1))               if bath_m else None
                    sqft      = int(sqft_m.group(1).replace(",","")) if sqft_m else None
                    unit_type = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}.get(beds,"Unknown")

                    # Apartment cards: div.card-body (partial match catches "card-body text-center")
                    apt_cards = [
                        c for c in soup.find_all("div", class_="card-body")
                        if "Apartment:" in c.get_text()
                    ]
                    logger.info(f"[The Montgomery] {fp_name}: {len(apt_cards)} apartment card(s)")

                    for card in apt_cards:
                        card_text = card.get_text(separator=" ", strip=True)

                        apt_m  = re.search(r"Apartment:\s*#\s*(\w+)", card_text, re.IGNORECASE)
                        date_m = re.search(r"Date Available:\s*([\d/]+)", card_text, re.IGNORECASE)
                        rent_m = re.search(r"Starting at:\s*\$([\d,]+)\s*/Month", card_text, re.IGNORECASE)

                        if not apt_m:
                            continue
                        unit_num = apt_m.group(1).strip()
                        if unit_num in seen_units:
                            continue
                        seen_units.add(unit_num)

                        try:
                            rent = float(rent_m.group(1).replace(",","")) if rent_m else None
                        except Exception:
                            rent = None

                        if not rent or rent < 500:
                            continue

                        avail_raw = date_m.group(1) if date_m else None
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
                        logger.debug(
                            f"[The Montgomery] ✓ #{unit_num} | {fp_name} | "
                            f"{unit_type} | ${rent} | {avail_str}"
                        )

                except Exception as e:
                    logger.error(f"[The Montgomery] Error on {fp_url}: {e}")

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
