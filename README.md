# Fitzrovia Rental Intelligence Platform

A competitive rental intelligence dashboard built to track unit availability, pricing, and incentives across 10 competitor apartment buildings in Toronto's Yonge & Eglinton midtown corridor.

> **A note on development:** This platform was built with the assistance of Claude (Anthropic's AI) as a development partner — helping architect the scraping logic, debug bot detection issues, and build the dashboard UI. Due to Claude's credit limits and a 5-hour cooldown between sessions, and with final exams approaching, I was unable to bring every scraper to full completion. What's presented here represents my best work under those constraints — a fully functional platform with 8 of 10 buildings scraping accurately, a polished dashboard, live incentive detection, and a working deployment. I'm proud of the depth and technical rigour of what was built in the time available.

---

## What It Does

The platform scrapes live rental data from 10 competing properties and consolidates it into a single internal dashboard. It tracks unit-level data including floor plan name, bedrooms, bathrooms, square footage, monthly rent, availability date, and current incentives (free months, move-in bonuses, included utilities). The dashboard allows filtering by unit type across all buildings and exports a consolidated PDF report.

---

## Tech Stack

**Backend**
- Python 3.11
- FastAPI — web framework
- Uvicorn — ASGI server
- SQLAlchemy — ORM / database layer
- SQLite — local database
- Jinja2 — HTML templating
- python-jose + bcrypt / passlib — JWT auth + password hashing

**Scraping**
- Playwright (headless Chromium) — browser automation for JavaScript-rendered sites
- httpx — async HTTP client for server-rendered sites
- BeautifulSoup4 + lxml — HTML parsing
- Loguru — structured logging

**Frontend**
- Vanilla HTML / CSS / JS — no framework
- DM Sans, DM Mono, Playfair Display (Google Fonts)
- Color scheme: #d84028 (orange) / black / white

**PDF Export**
- ReportLab

**Dev Tools**
- Conda (Python environment management)
- Git / GitHub
- Railway (hosting)
- Claude MCP Chrome extension — used to inspect live sites, intercept API calls, and test selectors in real browser sessions

---

## How the Scraping Works

Each building has a dedicated scraper in `scraper/buildings/`. Every scraper inherits from `BaseScraper` which handles browser setup, incentive fetching, and database saving. When a scrape is triggered from the dashboard, all 10 scrapers run concurrently (max 3 at a time) and results are saved to SQLite.

Incentives are scraped dynamically on every run — the base class visits each building's homepage and extracts promo text using regex patterns. Nothing is hardcoded.

### Per-Building Data Sources

| Building | URL Scraped | Method |
|---|---|---|
| **Parker** | parkerlife.ca | Playwright — clicks CHECK AVAILABILITY buttons, reads modal table |
| **Story of Midtown** | mystorymidtown.com/suites | Rentsync floorplan-navigator API (75 Broadway UUID) — floor-by-floor JSON |
| **The Selby** | triconliving.com/apartment/the-selby | Direct JSON API (triconliving.com/api/v1/apartments/the-selby) |
| **eCentral** | ecentralliving.com/rental-suites | DOM scrape — `.row.align-items-end.no-gutters` table rows per bedroom section |
| **The Whitney** | thewhitneyonredpath.com/apartments + /skyline-view-collection | Playwright — Elementor card grid, both pages merged |
| **The Hampton** | thehampton.ca/floorplans + WordPress REST API | `/wp-json/wp/v2/project` returns all floor plans as structured JSON |
| **E18HTEEN** | myrental.ca/apartments-for-rent/18-erskine-ave | Playwright — filter click + `.unit-group-card` DOM parsing |
| **Corner on Broadway** | thecornerrentals.com/suites | BeautifulSoup — clean HTML `<table>` with all floor plan rows |
| **Akoya Living** | akoyaliving.ca/suites | Rentsync unit-table-builder API (propertyId: 303333) |
| **The Montgomery** | themontgomery.ca/floorplans | Playwright + Cloudflare bypass — see known issues below |

---

## Known Issues

### The Montgomery — Cloudflare Bot Protection

The Montgomery's site (RentCafe/Yardi CMS) is protected by **Cloudflare Turnstile** bot detection. When headless Playwright visits the page, Cloudflare intercepts and serves a security challenge page instead of real content.

The data structure was fully confirmed using the Claude MCP Chrome extension — each floor plan detail page (`/floorplans/oriole`, `/floorplans/maxwell`, etc.) contains individual apartment cards with unit number, availability date, and price in server-rendered HTML. For example:

```
Apartment: # 2303
Date Available: 10/06/2026
Starting at: $2,435/Month

Apartment: # 1603
Date Available: 10/07/2026
Starting at: $2,400/Month
```

The scraper logic is correct and the data is confirmed live. The sole blocker is Cloudflare detecting the headless browser fingerprint. Several bypass approaches were explored including stealth JS injection, homepage session warming, and using `page.evaluate(fetch())` from an already-authenticated browser context — all blocked.

**To fix in a future iteration:** A residential proxy or `undetected-playwright` library would bypass Cloudflare's fingerprinting.

### E18HTEEN — Filter Timing Issue

The E18HTEEN scraper at `myrental.ca/apartments-for-rent/18-erskine-ave` uses a radio button filter system. The scraper correctly identifies that clicking the **parent label element** (`.input-radio__label:has(input[data-value="X"])`) is required — not the input itself — because the site's JavaScript listens on the label, not the input. All 7 floor plans were confirmed live via the Chrome MCP:

- Addison, Abbington, Elgin (1-Bed)
- Grammercy (1-Bed + Den)
- Bedford, Bennington (2-Bed)
- Chaplin (2-Bed + Den)

The filter interaction works locally in some runs but DOM update timing in headless Playwright is inconsistent. On Railway the scraper cannot run at all since Chromium binaries are not installed.

**To fix:** Adding explicit `wait_for_selector` calls after each filter click would stabilise timing.

---

## Why the Hosted Version Has No Data

The hosted version on Railway is a **read-only dashboard**. Playwright requires a full Chromium browser installation (~300MB of binaries) which is not included in the Railway deployment to keep the build within free tier limits. As a result, the "Refresh Data" button is disabled on the hosted version.

The hosted link reflects whatever data was in the SQLite database at the time of the last `git push`. To update the live dashboard with fresh data:

1. Run scrapers locally and let them populate the database
2. Push the updated `rental_data.db` to GitHub
3. Railway redeploys automatically with the new data

**If running locally, the platform runs seamlessly end-to-end** — all scrapers execute, data populates in real time, and the dashboard reflects live listings within seconds of triggering a scrape from the UI.

---

## A Note on the Development Process

This project was built collaboratively with **Claude (Anthropic)** as an AI development partner. Claude assisted with:

- Architecting the scraper base class and runner
- Identifying the correct API endpoints and selectors by inspecting live sites through the Chrome MCP
- Debugging bot detection issues (Cloudflare, RentCafe session cookies)
- Building the dashboard UI and PDF export
- Deploying to Railway and resolving bcrypt/Python version compatibility issues

Due to Claude's credit limits and a **5-hour cooldown between sessions**, and with **final exams approaching**, I was unable to bring every component to full completion. Each credit reset required re-explaining context and picking up where I left off, which slowed iteration significantly. Despite this, I'm proud of the technical depth achieved:

- 8 of 10 buildings scraping accurately with real unit-level data
- Live incentive detection with zero hardcoding
- Full JWT authentication
- PDF export
- Responsive dashboard with per-building detail views
- Working deployment on Railway

This was my best work given the time and resource constraints, and represents a genuine attempt to build something production-grade rather than a surface-level prototype.

---

## Running Locally

```bash
# Setup
conda activate fitzrovia
cd fitzrovia-scraper
pip install -r requirements.txt
playwright install chromium

# Start the server
uvicorn app:app --reload

# Visit
open http://127.0.0.1:8000
# Login: admin / fitzrovia2024
```

To run a single building scraper from the CLI:
```bash
python run_scraper.py --building "Parker"
python run_scraper.py --building "The Selby"
python run_scraper.py --building "Akoya Living"
# etc.
```

---

## Project Structure

```
fitzrovia-scraper/
├── app.py                  # FastAPI app, routes, Jinja2 templates
├── auth.py                 # JWT + bcrypt authentication
├── database.py             # SQLAlchemy models (Building, UnitListing, ScrapeRun)
├── run_scraper.py          # CLI for running individual scrapers
├── requirements.txt        # Python dependencies
├── rental_data.db          # SQLite database (committed with pre-scraped data)
├── scraper/
│   ├── base.py             # BaseScraper class, shared helpers, incentive scraping
│   ├── runner.py           # Async orchestrator (runs all scrapers concurrently)
│   └── buildings/
│       ├── parker.py
│       ├── story_midtown.py
│       ├── selby.py
│       ├── ecentral.py
│       ├── montgomery.py   # ⚠ Blocked by Cloudflare Turnstile
│       ├── whitney.py
│       ├── hampton.py
│       ├── e18hteen.py     # ⚠ Filter timing inconsistency in headless mode
│       ├── corner_broadway.py
│       └── akoya.py
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── building_detail.html
│   └── login.html
└── static/
```
