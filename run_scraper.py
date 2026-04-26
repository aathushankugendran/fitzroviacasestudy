#!/usr/bin/env python3
"""
run_scraper.py — standalone CLI to trigger a scrape.

Usage:
    python run_scraper.py                    # Run all 10 buildings
    python run_scraper.py --building Parker  # Run a single building
    python run_scraper.py --list             # List available scrapers
"""

import asyncio
import argparse
import sys
from loguru import logger
from database import create_tables, SessionLocal, seed_buildings
from scraper.buildings import ALL_SCRAPERS
from scraper.runner import run_all_scrapers, start_scrape_run


def list_scrapers():
    print("\nAvailable building scrapers:")
    for cls in ALL_SCRAPERS:
        inst = cls()
        print(f"  • {inst.building_name} — {inst.url}")
    print()


async def run_single(building_name: str):
    """Run scraper for one building by name."""
    target = None
    for cls in ALL_SCRAPERS:
        inst = cls()
        if inst.building_name.lower() == building_name.lower():
            target = cls
            break

    if not target:
        logger.error(f"No scraper found for '{building_name}'. Use --list to see options.")
        sys.exit(1)

    scraper = target()
    logger.info(f"Running scraper for: {scraper.building_name}")
    units = await scraper.scrape()

    if not units:
        logger.warning("No units found.")
    else:
        logger.success(f"Found {len(units)} unit(s):")
        for u in units:
            rent_str = f"${u.monthly_rent:,.0f}/mo" if u.monthly_rent else "rent N/A"
            sqft_str = f"{u.sq_ft} sqft" if u.sq_ft else "sqft N/A"
            print(f"  [{u.unit_type}] {rent_str} | {sqft_str} | {u.incentives or 'no incentives'}")


def main():
    parser = argparse.ArgumentParser(description="Fitzrovia Rental Scraper")
    parser.add_argument("--building", type=str, help="Name of a specific building to scrape")
    parser.add_argument("--list", action="store_true", help="List all available scrapers")
    args = parser.parse_args()

    # Ensure DB exists
    create_tables()
    db = SessionLocal()
    seed_buildings(db)
    db.close()

    if args.list:
        list_scrapers()
        return

    if args.building:
        asyncio.run(run_single(args.building))
    else:
        logger.info("Running all 10 building scrapers...")
        run_id = start_scrape_run()
        results = asyncio.run(run_all_scrapers(run_id))
        print(f"\n{'='*50}")
        print(f"  Scrape complete")
        print(f"  Buildings scraped : {results['buildings_scraped']}")
        print(f"  Total units found : {results['units_found']}")
        if results["errors"]:
            print(f"  Errors           : {len(results['errors'])}")
            for e in results["errors"]:
                print(f"    - {e}")
        print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
