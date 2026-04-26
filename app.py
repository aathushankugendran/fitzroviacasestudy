"""
app.py — FastAPI web application.

Routes:
  GET  /login         Login page
  POST /login         Authenticate
  GET  /logout        Clear cookie
  GET  /              Dashboard (requires auth)
  GET  /buildings/{id} Building detail (requires auth)
  POST /scrape        Trigger a fresh scrape (requires auth)
  GET  /scrape/status Check scrape status
  GET  /export/pdf    Download consolidated PDF report
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/Toronto")  # Eastern Time (handles DST automatically)

def to_et(dt: datetime) -> datetime:
    """Convert UTC datetime to Eastern Time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ET)
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from loguru import logger

from database import (
    create_tables, get_db, seed_buildings,
    Building, UnitListing, ScrapeRun, SessionLocal
)
from auth import (
    authenticate_user, create_access_token, require_auth,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from pdf_export import generate_rental_report

app = FastAPI(title="Fitzrovia Rental Intelligence")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Register ET timezone filter for templates
def fmt_et(dt, fmt="%b %d, %H:%M ET"):
    if dt is None:
        return "—"
    return to_et(dt).strftime(fmt)

templates.env.filters["et"] = fmt_et

# Track running scrape so we don't double-start
_scrape_running = False


@app.on_event("startup")
def startup():
    create_tables()
    db = SessionLocal()
    seed_buildings(db)
    db.close()


# --------------------------------------------------------------------------- #
# Auth routes                                                                  #
# --------------------------------------------------------------------------- #

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    # Already logged in → redirect
    token = request.cookies.get("access_token")
    if token:
        from auth import decode_token
        if decode_token(token):
            return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not authenticate_user(username, password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )
    token = create_access_token(
        {"sub": username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("access_token")
    return response


# --------------------------------------------------------------------------- #
# Dashboard                                                                    #
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    unit_type: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    buildings = db.query(Building).all()

    # Build summary cards
    building_summaries = []
    for b in buildings:
        units = (
            db.query(UnitListing)
            .filter(UnitListing.building_id == b.id, UnitListing.is_available == True)
            .all()
        )
        rents = [u.monthly_rent for u in units if u.monthly_rent]
        incentives = next((u.incentives for u in units if u.incentives), None)
        building_summaries.append({
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "url": b.url,
            "last_scraped_at": b.last_scraped_at,
            "scrape_status": b.scrape_status,
            "unit_count": len(units),
            "min_rent": min(rents) if rents else None,
            "max_rent": max(rents) if rents else None,
            "bachelor_count": sum(1 for u in units if u.bedrooms == 0),
            "one_bed_count": sum(1 for u in units if u.bedrooms == 1),
            "two_bed_count": sum(1 for u in units if u.bedrooms == 2),
            "three_bed_count": sum(1 for u in units if u.bedrooms == 3),
            "incentives": incentives,
        })

    # Grouped view by unit type
    unit_type_filter = unit_type or None
    q = db.query(UnitListing).join(Building)
    if unit_type_filter:
        q = q.filter(UnitListing.unit_type == unit_type_filter)
    all_units = q.order_by(UnitListing.unit_type, UnitListing.monthly_rent).all()

    # Attach building name
    bldg_map = {b.id: b.name for b in buildings}
    units_with_building = []
    for u in all_units:
        units_with_building.append({
            "id": u.id,
            "building_name": bldg_map.get(u.building_id, ""),
            "building_id": u.building_id,
            "unit_number": u.unit_number,
            "unit_type": u.unit_type,
            "bedrooms": u.bedrooms,
            "floor_plan_name": u.floor_plan_name,
            "monthly_rent": u.monthly_rent,
            "sq_ft": u.sq_ft,
            "available_date": u.available_date,
            "incentives": u.incentives,
            "scraped_at": u.scraped_at,
        })

    # Last scrape run
    last_run = db.query(ScrapeRun).order_by(ScrapeRun.id.desc()).first()

    # Unit type counts for filter pills
    type_counts = {}
    for ut in ["Bachelor", "1-Bed", "2-Bed", "3-Bed"]:
        type_counts[ut] = db.query(UnitListing).filter(UnitListing.unit_type == ut).count()

    total_units = db.query(UnitListing).count()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "buildings": building_summaries,
        "units": units_with_building,
        "unit_type": unit_type,
        "type_counts": type_counts,
        "total_units": total_units,
        "last_run": last_run,
        "scrape_running": _scrape_running,
        "now": datetime.utcnow(),
    })


# --------------------------------------------------------------------------- #
# Building detail                                                              #
# --------------------------------------------------------------------------- #

@app.get("/buildings/{building_id}", response_class=HTMLResponse)
async def building_detail(
    request: Request,
    building_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    units = (
        db.query(UnitListing)
        .filter(UnitListing.building_id == building_id)
        .order_by(UnitListing.bedrooms, UnitListing.monthly_rent)
        .all()
    )

    rents = [u.monthly_rent for u in units if u.monthly_rent]
    sqfts = [u.sq_ft for u in units if u.sq_ft]

    return templates.TemplateResponse("building_detail.html", {
        "request": request,
        "user": user,
        "building": building,
        "units": units,
        "unit_count": len(units),
        "min_rent": min(rents) if rents else None,
        "max_rent": max(rents) if rents else None,
        "avg_rent": sum(rents) / len(rents) if rents else None,
        "avg_sqft": int(sum(sqfts) / len(sqfts)) if sqfts else None,
    })


# --------------------------------------------------------------------------- #
# Scrape trigger                                                                #
# --------------------------------------------------------------------------- #

@app.post("/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    user: str = Depends(require_auth),
):
    global _scrape_running
    if _scrape_running:
        return JSONResponse({"status": "already_running"})

    _scrape_running = True
    background_tasks.add_task(_run_scrape_background)
    return JSONResponse({"status": "started"})


async def _run_scrape_background():
    global _scrape_running
    try:
        from scraper.runner import run_all_scrapers, start_scrape_run
        run_id = start_scrape_run()
        results = await run_all_scrapers(run_id)
        logger.info(f"Background scrape complete: {results}")
    except Exception as e:
        logger.error(f"Background scrape error: {e}")
    finally:
        _scrape_running = False


@app.get("/scrape/status")
async def scrape_status(user: str = Depends(require_auth), db: Session = Depends(get_db)):
    last_run = db.query(ScrapeRun).order_by(ScrapeRun.id.desc()).first()
    return JSONResponse({
        "running": _scrape_running,
        "last_run": {
            "id": last_run.id,
            "started_at": last_run.started_at.isoformat() if last_run and last_run.started_at else None,
            "completed_at": last_run.completed_at.isoformat() if last_run and last_run.completed_at else None,
            "status": last_run.status if last_run else None,
            "units_found": last_run.units_found if last_run else 0,
            "buildings_scraped": last_run.buildings_scraped if last_run else 0,
        } if last_run else None,
    })


# --------------------------------------------------------------------------- #
# PDF Export                                                                   #
# --------------------------------------------------------------------------- #

@app.get("/export/pdf")
async def export_pdf(
    user: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    buildings = db.query(Building).all()
    building_summaries = []
    for b in buildings:
        units = db.query(UnitListing).filter(UnitListing.building_id == b.id).all()
        rents = [u.monthly_rent for u in units if u.monthly_rent]
        incentives = next((u.incentives for u in units if u.incentives), None)
        building_summaries.append({
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "last_scraped_at": b.last_scraped_at,
            "unit_count": len(units),
            "min_rent": min(rents) if rents else None,
            "max_rent": max(rents) if rents else None,
            "bachelor_count": sum(1 for u in units if u.bedrooms == 0),
            "one_bed_count": sum(1 for u in units if u.bedrooms == 1),
            "two_bed_count": sum(1 for u in units if u.bedrooms == 2),
            "three_bed_count": sum(1 for u in units if u.bedrooms == 3),
            "incentives": incentives,
        })

    all_units = db.query(UnitListing).join(Building).all()
    bldg_map = {b.id: b.name for b in buildings}

    units_by_type = {"Bachelor": [], "1-Bed": [], "2-Bed": [], "3-Bed": []}
    for u in all_units:
        if u.unit_type in units_by_type:
            units_by_type[u.unit_type].append({
                "building_name": bldg_map.get(u.building_id, ""),
                "unit_number": u.unit_number,
                "floor_plan_name": u.floor_plan_name,
                "monthly_rent": u.monthly_rent,
                "sq_ft": u.sq_ft,
                "available_date": u.available_date,
                "incentives": u.incentives,
            })

    last_run = db.query(ScrapeRun).order_by(ScrapeRun.id.desc()).first()
    scraped_at = (
        to_et(last_run.completed_at).strftime("%B %d, %Y at %H:%M ET")
        if last_run and last_run.completed_at
        else to_et(datetime.now(timezone.utc)).strftime("%B %d, %Y at %H:%M ET")
    )

    pdf_bytes = generate_rental_report({
        "buildings": building_summaries,
        "units_by_type": units_by_type,
        "scraped_at": scraped_at,
        "total_units": len(all_units),
    })

    filename = f"fitzrovia_rental_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )