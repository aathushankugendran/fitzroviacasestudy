"""
Base scraper class — all building scrapers inherit from this.
Provides shared browser setup, helpers, and the UnitData model.
"""

import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


@dataclass
class UnitData:
    unit_number: Optional[str] = None
    unit_type: str = "Unknown"
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    floor_plan_name: Optional[str] = None
    monthly_rent: Optional[float] = None
    rent_min: Optional[float] = None
    rent_max: Optional[float] = None
    sq_ft: Optional[int] = None
    sq_ft_min: Optional[int] = None
    sq_ft_max: Optional[int] = None
    floor: Optional[int] = None
    available_date: Optional[str] = None
    is_available: bool = True
    incentives: Optional[str] = None
    source_url: Optional[str] = None


# Incentive patterns — ordered by specificity
_INCENTIVE_PATTERNS = [
    r"(up to \d+\s*months?\s*(?:rent\s*)?free[^.\n]{0,80})",
    r"(\d+\s*months?\s*(?:rent\s*)?free[^.\n]{0,80})",
    r"(\d+\s*weeks?\s*free[^.\n]{0,60})",
    r"(\$[\d,]+\s*(?:move-?in|signing|bonus)[^.\n]{0,60})",
    r"(move-?in\s*bonus[^.\n]{0,60})",
    r"(free\s+(?:bell|rogers|internet|wifi|wi-fi|gigabit)[^.\n]{0,60})",
    r"(complimentary\s+(?:wi-?fi|internet|gift)[^.\n]{0,60})",
    r"(waived?\s+(?:deposit|fee|application)[^.\n]{0,60})",
    r"(no\s+(?:deposit|application\s*fee)[^.\n]{0,60})",
    r"(utilities?\s+included[^.\n]{0,40})",
]

# Incentive homepage URLs (confirmed live from Chrome)
_INCENTIVE_URLS = {
    "Parker":             "https://www.parkerlife.ca",
    "Story of Midtown":   "https://www.mystorymidtown.com",
    "The Selby":          "https://triconliving.com/apartment/the-selby/",
    "eCentral":           "https://www.ecentralliving.com",
    "The Montgomery":     "https://www.themontgomery.ca",
    "The Whitney":        "https://www.thewhitneyonredpath.com",
    "The Hampton":        "https://thehampton.ca",
    "E18HTEEN":           "https://www.myrental.ca/apartments-for-rent/18-erskine-ave",
    "Corner on Broadway": "https://thecornerrentals.com",
    "Akoya Living":       "https://www.akoyaliving.ca",
}


class BaseScraper:
    building_name: str = "Unknown"
    building_address: str = ""
    url: str = ""

    TIMEOUT = 30_000
    NAV_TIMEOUT = 45_000
    HEADLESS = True

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def _start_browser(self, playwright):
        self._browser = await playwright.chromium.launch(
            headless=self.HEADLESS,
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
        await self._context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
            lambda route: route.abort(),
        )

    async def _new_page(self) -> Page:
        page = await self._context.new_page()
        page.set_default_timeout(self.TIMEOUT)
        page.set_default_navigation_timeout(self.NAV_TIMEOUT)
        return page

    async def _close_browser(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    async def scrape(self) -> list[UnitData]:
        """Run the scraper — scrapes units then fetches live incentives."""
        logger.info(f"[{self.building_name}] Starting scrape → {self.url}")
        units: list[UnitData] = []
        async with async_playwright() as pw:
            try:
                await self._start_browser(pw)

                # 1. Scrape units
                units = await self._do_scrape()
                logger.success(f"[{self.building_name}] Found {len(units)} units")

                # 2. Fetch live incentives from homepage
                incentive = await self._fetch_incentives_live()
                if incentive:
                    for u in units:
                        u.incentives = incentive
                    logger.info(f"[{self.building_name}] Incentive: {incentive}")

            except Exception as exc:
                logger.error(f"[{self.building_name}] Scrape failed: {exc}")
            finally:
                await self._close_browser()
        return units

    async def _fetch_incentives_live(self) -> Optional[str]:
        """Visit the building homepage and extract current promotions."""
        url = _INCENTIVE_URLS.get(self.building_name)
        if not url:
            return None
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            text = await page.inner_text("body")
            text = re.sub(r'\s+', ' ', text)
            return self.extract_incentives(text)
        except Exception as e:
            logger.debug(f"[{self.building_name}] Incentive fetch error: {e}")
            return None
        finally:
            await page.close()

    async def _do_scrape(self) -> list[UnitData]:
        raise NotImplementedError

    # ── Shared helpers ──────────────────────────────────────────────────

    @staticmethod
    def parse_rent(text: str) -> Optional[float]:
        if not text:
            return None
        text = text.replace(",", "").replace("\u00a0", "")
        match = re.search(r"\$?\s*(\d+(?:\.\d{2})?)", text)
        return float(match.group(1)) if match else None

    @staticmethod
    def parse_sqft(text: str) -> Optional[int]:
        if not text:
            return None
        text = text.replace(",", "").replace("\u00a0", "")
        match = re.search(r"(\d{3,4})", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def normalize_unit_type(raw: str) -> tuple[str, int]:
        if not raw:
            return ("Unknown", -1)
        raw_lower = raw.lower()
        if any(w in raw_lower for w in ("bachelor", "studio", "0 bed", "0-bed")):
            return ("Bachelor", 0)
        if "3" in raw_lower and "bed" in raw_lower:
            return ("3-Bed", 3)
        if "2" in raw_lower and "bed" in raw_lower:
            return ("2-Bed", 2)
        if "1" in raw_lower and "bed" in raw_lower:
            return ("1-Bed", 1)
        digit = re.search(r"(\d)", raw_lower)
        if digit:
            n = int(digit.group(1))
            if n == 0:
                return ("Bachelor", 0)
            return (f"{n}-Bed", n)
        return ("Unknown", -1)

    @staticmethod
    def extract_incentives(page_text: str) -> Optional[str]:
        """Extract promo/incentive text from raw page content."""
        if not page_text:
            return None
        found = []
        seen_keys = set()
        for pat in _INCENTIVE_PATTERNS:
            matches = re.findall(pat, page_text, re.IGNORECASE)
            for m in matches:
                m = re.sub(r'\s+', ' ', m).strip()
                if len(m) > 100:
                    m = m[:100].rsplit(' ', 1)[0]
                key = m.lower()[:40]
                if key not in seen_keys and len(m) > 8:
                    seen_keys.add(key)
                    found.append(m)
            if len(found) >= 3:
                break
        return "; ".join(found) if found else None