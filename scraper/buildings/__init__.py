"""
Safe scraper imports — if one file has an error it won't break the others.
"""

from loguru import logger

ALL_SCRAPERS = []

def _safe_import(module_path, class_name):
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        ALL_SCRAPERS.append(cls)
    except Exception as e:
        logger.error(f"Failed to import {class_name} from {module_path}: {e}")

_safe_import("scraper.buildings.parker",          "ParkerScraper")
_safe_import("scraper.buildings.story_midtown",   "StoryMidtownScraper")
_safe_import("scraper.buildings.selby",           "SelbyScraper")
_safe_import("scraper.buildings.ecentral",        "ECentralScraper")
_safe_import("scraper.buildings.montgomery",      "MontgomeryScraper")
_safe_import("scraper.buildings.whitney",         "WhitneyScraper")
_safe_import("scraper.buildings.hampton",         "HamptonScraper")
_safe_import("scraper.buildings.e18hteen",        "E18HTEENScraper")
_safe_import("scraper.buildings.corner_broadway", "CornerBroadwayScraper")
_safe_import("scraper.buildings.akoya",           "AkoyaScraper")

logger.info(f"Loaded {len(ALL_SCRAPERS)} scrapers: {[s.building_name for s in ALL_SCRAPERS]}")
