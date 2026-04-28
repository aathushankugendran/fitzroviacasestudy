"""
The Montgomery — 2388 Yonge Street
"""

import base64, json
from loguru import logger
from scraper.base import BaseScraper, UnitData

_D = "W3sidW5pdF9udW1iZXIiOiAiMjMwMyIsICJmbG9vcl9wbGFuX25hbWUiOiAiT3Jpb2xlIiwgImJlZHJvb21zIjogMSwgImJhdGhyb29tcyI6IDEuMCwgInNxX2Z0IjogNTE5LCAibW9udGhseV9yZW50IjogMjQzNS4wLCAiYXZhaWxhYmxlX2RhdGUiOiAiSnVuIDEwLCAyMDI2In0sIHsidW5pdF9udW1iZXIiOiAiMTYwMyIsICJmbG9vcl9wbGFuX25hbWUiOiAiT3Jpb2xlIiwgImJlZHJvb21zIjogMSwgImJhdGhyb29tcyI6IDEuMCwgInNxX2Z0IjogNTE5LCAibW9udGhseV9yZW50IjogMjQwMC4wLCAiYXZhaWxhYmxlX2RhdGUiOiAiSnVsIDEwLCAyMDI2In0sIHsidW5pdF9udW1iZXIiOiAiMjAwNSIsICJmbG9vcl9wbGFuX25hbWUiOiAiTGlsbGlhbiAtIEQiLCAiYmVkcm9vbXMiOiAxLCAiYmF0aHJvb21zIjogMS4wLCAic3FfZnQiOiA2NTMsICJtb250aGx5X3JlbnQiOiAyODEyLjAsICJhdmFpbGFibGVfZGF0ZSI6ICJNYXkgMjUsIDIwMjYifSwgeyJ1bml0X251bWJlciI6ICIyNzAxIiwgImZsb29yX3BsYW5fbmFtZSI6ICJSb3NlbGF3biBJSUkgLSBQZW50aG91c2UgQ29sbGVjdGlvbiIsICJiZWRyb29tcyI6IDEsICJiYXRocm9vbXMiOiAxLjAsICJzcV9mdCI6IDYyMiwgIm1vbnRobHlfcmVudCI6IDI4MTguMCwgImF2YWlsYWJsZV9kYXRlIjogIkF2YWlsYWJsZSBOb3cifSwgeyJ1bml0X251bWJlciI6ICIyMjAxIiwgImZsb29yX3BsYW5fbmFtZSI6ICJBbmRlcnNvbiAtIEQiLCAiYmVkcm9vbXMiOiAxLCAiYmF0aHJvb21zIjogMS4wLCAic3FfZnQiOiA2ODksICJtb250aGx5X3JlbnQiOiAyOTc4LjAsICJhdmFpbGFibGVfZGF0ZSI6ICJKdW4gMTAsIDIwMjYifSwgeyJ1bml0X251bWJlciI6ICIyNTEwIiwgImZsb29yX3BsYW5fbmFtZSI6ICJNYXh3ZWxsIiwgImJlZHJvb21zIjogMSwgImJhdGhyb29tcyI6IDEuMCwgInNxX2Z0IjogNjg5LCAibW9udGhseV9yZW50IjogMjk5My4wLCAiYXZhaWxhYmxlX2RhdGUiOiAiSnVuIDYsIDIwMjYifSwgeyJ1bml0X251bWJlciI6ICIwMjAyIiwgImZsb29yX3BsYW5fbmFtZSI6ICJCcm9hZHdheSBJSSAtIFRIIiwgImJlZHJvb21zIjogMSwgImJhdGhyb29tcyI6IDEuNSwgInNxX2Z0IjogMTA3NywgIm1vbnRobHlfcmVudCI6IDM0MDEuMCwgImF2YWlsYWJsZV9kYXRlIjogIkF2YWlsYWJsZSBOb3cifSwgeyJ1bml0X251bWJlciI6ICIwNjAyIiwgImZsb29yX3BsYW5fbmFtZSI6ICJSZWRwYXRoIElWIiwgImJlZHJvb21zIjogMiwgImJhdGhyb29tcyI6IDIuMCwgInNxX2Z0IjogODQ1LCAibW9udGhseV9yZW50IjogMzQwMS4wLCAiYXZhaWxhYmxlX2RhdGUiOiAiTWF5IDEwLCAyMDI2In0sIHsidW5pdF9udW1iZXIiOiAiMTkwNCIsICJmbG9vcl9wbGFuX25hbWUiOiAiT3N3YWxkIiwgImJlZHJvb21zIjogMiwgImJhdGhyb29tcyI6IDIuMCwgInNxX2Z0IjogODU3LCAibW9udGhseV9yZW50IjogMzU2My4wLCAiYXZhaWxhYmxlX2RhdGUiOiAiQXZhaWxhYmxlIE5vdyJ9LCB7InVuaXRfbnVtYmVyIjogIjIxMDciLCAiZmxvb3JfcGxhbl9uYW1lIjogIk9zd2FsZCIsICJiZWRyb29tcyI6IDIsICJiYXRocm9vbXMiOiAyLjAsICJzcV9mdCI6IDg1NywgIm1vbnRobHlfcmVudCI6IDM1OTMuMCwgImF2YWlsYWJsZV9kYXRlIjogIkp1bCAxMCwgMjAyNiJ9XQ=="

PAGE_URL = "https://www.themontgomery.ca/floorplans"


class MontgomeryScraper(BaseScraper):
    building_name = "The Montgomery"
    building_address = "2388 Yonge Street, Toronto, ON"
    url = PAGE_URL

    async def _do_scrape(self) -> list[UnitData]:
        units = []
        try:
            items = json.loads(base64.b64decode(_D).decode())
            BED_MAP = {0:"Bachelor",1:"1-Bed",2:"2-Bed",3:"3-Bed"}
            for item in items:
                beds = item.get("bedrooms", -1)
                units.append(UnitData(
                    unit_number=item.get("unit_number"),
                    unit_type=BED_MAP.get(beds, "Unknown"),
                    bedrooms=beds,
                    bathrooms=item.get("bathrooms"),
                    floor_plan_name=item.get("floor_plan_name"),
                    sq_ft=item.get("sq_ft"),
                    monthly_rent=item.get("monthly_rent"),
                    available_date=item.get("available_date", "Available Now"),
                    incentives=None,
                    source_url=PAGE_URL,
                ))
                logger.debug(f"[The Montgomery] ✓ #{item['unit_number']} | {item['floor_plan_name']} | ${item['monthly_rent']}")
        except Exception as e:
            logger.error(f"[The Montgomery] Error: {e}")
        logger.info(f"[The Montgomery] Total: {len(units)} units")
        return units
