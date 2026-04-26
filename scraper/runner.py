"""
Scraper runner — orchestrates all 10 building scrapers.

Runs scrapers concurrently (with a semaphore to limit browser instances),
writes results to the database, and records the scrape run metadata.
"""

import asyncio
from datetime import datetime
from loguru import logger

from database import SessionLocal, Building, UnitListing, ScrapeRun, BUILDINGS_CONFIG
from scraper.buildings import ALL_SCRAPERS


# Limit concurrent browser instances to avoid OOM on smaller machines
MAX_CONCURRENT = 3


async def run_all_scrapers(run_id: int = None) -> dict:
    """
    Run all scrapers concurrently.
    Returns summary: {buildings_scraped, units_found, errors}.
    """
    db = SessionLocal()
    results = {"buildings_scraped": 0, "units_found": 0, "errors": []}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_one(ScraperClass):
        async with semaphore:
            scraper = ScraperClass()
            units = await scraper.scrape()
            return scraper.building_name, units

    tasks = [run_one(cls) for cls in ALL_SCRAPERS]
    scraped = await asyncio.gather(*tasks, return_exceptions=True)

    try:
        for result in scraped:
            if isinstance(result, Exception):
                results["errors"].append(str(result))
                continue

            building_name, units = result

            # Fetch building from DB
            building = db.query(Building).filter(Building.name == building_name).first()
            if not building:
                logger.warning(f"Building '{building_name}' not found in DB — skipping")
                continue

            # Clear old listings for this building
            db.query(UnitListing).filter(UnitListing.building_id == building.id).delete()

            # Insert new listings
            now = datetime.utcnow()
            for u in units:
                listing = UnitListing(
                    building_id=building.id,
                    unit_number=u.unit_number,
                    unit_type=u.unit_type,
                    bedrooms=u.bedrooms,
                    bathrooms=u.bathrooms,
                    floor_plan_name=u.floor_plan_name,
                    monthly_rent=u.monthly_rent,
                    rent_min=u.rent_min,
                    rent_max=u.rent_max,
                    sq_ft=u.sq_ft,
                    sq_ft_min=u.sq_ft_min,
                    sq_ft_max=u.sq_ft_max,
                    floor=u.floor,
                    available_date=u.available_date,
                    is_available=u.is_available,
                    incentives=u.incentives,
                    scraped_at=now,
                    source_url=u.source_url,
                )
                db.add(listing)

            # Update building scrape status
            building.last_scraped_at = now
            building.scrape_status = "success" if units else "empty"
            building.scrape_error = None

            results["buildings_scraped"] += 1
            results["units_found"] += len(units)
            logger.info(f"Saved {len(units)} units for {building_name}")

        db.commit()

        # Update scrape run record
        if run_id:
            run = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
            if run:
                run.completed_at = datetime.utcnow()
                run.status = "completed"
                run.buildings_scraped = results["buildings_scraped"]
                run.units_found = results["units_found"]
                run.errors = "; ".join(results["errors"]) if results["errors"] else None
                db.commit()

    except Exception as e:
        logger.error(f"Runner DB error: {e}")
        db.rollback()
        results["errors"].append(str(e))
    finally:
        db.close()

    return results


def start_scrape_run() -> int:
    """Create a new ScrapeRun record and return its ID."""
    db = SessionLocal()
    try:
        run = ScrapeRun(started_at=datetime.utcnow(), status="running")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    finally:
        db.close()


def run_scraper_sync() -> dict:
    """Synchronous wrapper — useful for calling from FastAPI background tasks."""
    run_id = start_scrape_run()
    return asyncio.run(run_all_scrapers(run_id))
