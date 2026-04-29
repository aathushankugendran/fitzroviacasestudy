# Fitzrovia Rental Intelligence Platform

**A live competitive rental intelligence dashboard tracking unit availability, pricing, and incentives across 10 competitor apartment buildings in Toronto's Yonge & Eglinton midtown corridor.**

🔗 **Live Dashboard:** [web-production-10bb7.up.railway.app](https://web-production-10bb7.up.railway.app)
📦 **Repository:** [github.com/aathushankugendran/fitzroviacasestudy](https://github.com/aathushankugendran/fitzroviacasestudy)

---

## Overview

This platform was built as an internal competitive intelligence tool for Fitzrovia Real Estate. It automates the collection of rental listing data from 10 competing properties in the Yonge & Eglinton submarket, aggregating unit-level pricing, availability, and incentive information into a single authenticated dashboard with PDF export capabilities.

The platform runs scrapers concurrently against a mix of APIs, server-rendered HTML, and JavaScript-heavy frontends — each requiring a tailored extraction approach. Data is stored in SQLite and surfaced through a FastAPI/Jinja2 dashboard with per-unit filtering, building detail views, and a formatted PDF report.

---

## What It Tracks

For every available unit across all 10 buildings, the platform captures:

- Floor plan name and unit number
- Bedroom and bathroom count
- Square footage
- Monthly rent (min/max where available)
- Availability date
- Active incentives (free months, move-in bonuses, included utilities)

Incentives are extracted dynamically on every scrape run — the base class visits each building's homepage and parses promotional text using regex patterns. Nothing is hardcoded.

---

## Tech Stack

### Backend

| Package | Version | Purpose |
|---|---|---|
| Python | 3.11 | Runtime |
| FastAPI | 0.115.0 | Web framework + REST API |
| Uvicorn | 0.30.6 | ASGI server |
| SQLAlchemy | 2.0.36 | ORM / database layer |
| SQLite | — | Local persistent database |
| Jinja2 | 3.1.4 | Server-side HTML templating |
| python-jose | 3.3.0 | JWT token generation + validation |
| bcrypt | 4.2.1 | Password hashing |

### Scraping

| Package | Version | Purpose |
|---|---|---|
| Playwright | 1.47.0 | Headless Chromium for JavaScript-rendered pages |
| httpx | 0.27.2 | Async HTTP client for API/server-rendered pages |
| BeautifulSoup4 | 4.12.3 | HTML parsing |
| lxml | 5.3.0 | Fast HTML parser backend |
| Loguru | 0.7.2 | Structured logging |
| tenacity | 9.0.0 | Retry logic |

### Frontend

- Vanilla HTML / CSS / JavaScript — no frontend framework
- Google Fonts: DM Sans, DM Mono, Playfair Display
- Color scheme: `#d84028` (brand orange), black, white

### PDF Export

- ReportLab 4.2.2 — programmatic PDF generation with custom table styling, section headers, and per-unit breakdowns by bedroom type

### Infrastructure

- **Railway** — cloud deployment (Docker-based, Playwright Chromium pre-installed)
- **Docker** — `mcr.microsoft.com/playwright/python:v1.47.0-jammy` base image
- **GitHub** — source control and CI/CD (Railway auto-deploys on push to `main`)
- **Conda** — Python environment management

---

## How the Scraping Works

### Architecture

Each building has a dedicated scraper module in `scraper/buildings/`. All scrapers inherit from `BaseScraper` (`scraper/base.py`) which provides:

- Playwright browser lifecycle management (launch, context, teardown)
- Stealth browser configuration to reduce bot detection (webdriver flag removal, plugin spoofing, locale injection)
- Shared incentive scraping via `_fetch_incentives_live()` — visits the building homepage and extracts promo text
- Database save logic
- Structured logging via Loguru

The runner (`scraper/runner.py`) orchestrates all scrapers asynchronously using `asyncio.Semaphore` with a concurrency cap of 3 simultaneous scrapers to manage memory on Railway's container.

### Trigger Flow

1. User clicks **Refresh Data** on the dashboard (or **↻** on an individual building card)
2. FastAPI receives a `POST /scrape` (all buildings) or `POST /scrape/building/{id}` (single building)
3. The scrape runs in the background via FastAPI's `BackgroundTasks`
4. The frontend polls `GET /scrape/status` every 2 seconds and auto-reloads when the run completes

### Per-Building Data Sources

| Building | URL | Method |
|---|---|---|
| **Parker** | parkerlife.ca/floorplans | Playwright — clicks 10 `CHECK AVAILABILITY` buttons, reads modal tables |
| **Story of Midtown** | mystorymidtown.com/suites | Rentsync floorplan-navigator XHR API (property UUID: `6d6e564e`, 75 Broadway) — intercepts the XHR fired on page load |
| **The Selby** | triconliving.com/apartment/the-selby | Direct JSON API — `triconliving.com/api/v1/apartments/the-selby` returns full unit + floorplan data |
| **eCentral** | ecentralliving.com/rental-suites | BeautifulSoup DOM scrape — `.row.align-items-end.no-gutters` card sections per bedroom category |
| **The Whitney** | thewhitneyonredpath.com/apartments + /skyline-view-collection | Playwright — Elementor card grid across two pages, merged into single result set |
| **The Hampton** | thehampton.ca/floorplans | WordPress REST API — `GET /wp-json/wp/v2/project?per_page=100` returns all floor plan posts as structured JSON |
| **E18HTEEN** | myrental.ca/apartments-for-rent/18-erskine-ave | Rentsync unit-table-builder API (propertyId: 33874, siteKey: kg_rebuild) — no browser required |
| **Corner on Broadway** | thecornerrentals.com/suites | BeautifulSoup — parses a clean HTML `<table>` containing all floor plan rows |
| **Akoya Living** | akoyaliving.ca/suites | Rentsync unit-table-builder API (propertyId: 303333) — direct httpx call |
| **The Montgomery** | themontgomery.ca/floorplans | Playwright with stealth configuration — see Known Issues |

---

## Dashboard Features

- **Overview cards** — all 10 buildings at a glance with unit counts by bedroom type, rent range, incentive badge, and last-scraped timestamp
- **Per-building refresh** — `↻` button on each card triggers a single-building scrape without re-running all 10
- **Unit type filter** — filter across all buildings simultaneously by Bachelor / 1-Bed / 2-Bed / 3-Bed
- **Building detail view** — full unit table per building with floor plan name, unit number, sqft, bathrooms, monthly rent, availability date, and incentives
- **PDF export** — formatted competitive report with building summary table and per-unit breakdowns grouped by bedroom count, generated server-side with ReportLab
- **JWT authentication** — login-gated dashboard; all routes require a valid session cookie

---

## Project Structure

```
fitzroviacasestudy/
├── app.py                    # FastAPI routes, auth middleware, scrape triggers, Jinja2 rendering
├── auth.py                   # JWT generation + bcrypt compatibility patch for passlib
├── database.py               # SQLAlchemy models: Building, UnitListing, ScrapeRun
├── pdf_export.py             # ReportLab PDF generation — tables, section headers, footer
├── run_scraper.py            # CLI entry point for running individual scrapers
├── requirements.txt          # Pinned Python dependencies
├── Dockerfile                # Playwright-capable Docker image (mcr.microsoft.com base)
├── fitzrovia.db              # SQLite database
│
├── scraper/
│   ├── base.py               # BaseScraper — Playwright setup, stealth, incentive fetch, DB write
│   ├── runner.py             # Async orchestrator with asyncio.Semaphore (max 3 concurrent)
│   └── buildings/
│       ├── __init__.py       # Safe dynamic imports — one broken scraper won't disable others
│       ├── parker.py
│       ├── story_midtown.py
│       ├── selby.py
│       ├── ecentral.py
│       ├── montgomery.py
│       ├── whitney.py
│       ├── hampton.py
│       ├── e18hteen.py
│       ├── corner_broadway.py
│       └── akoya.py
│
└── templates/
    ├── base.html             # Shared layout, nav, fonts, CSS variables
    ├── dashboard.html        # Building cards, filters, refresh logic, status polling
    ├── building_detail.html  # Per-building unit table with sorting
    └── login.html            # JWT login form
```

---

## Running Locally

### Prerequisites

- Python 3.11 (via Conda or venv)
- Git

### Setup

```bash
git clone https://github.com/aathushankugendran/fitzroviacasestudy.git
cd fitzroviacasestudy

# Create environment
conda create -n fitzrovia python=3.11
conda activate fitzrovia

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Start the server
uvicorn app:app --reload
```

Visit `http://127.0.0.1:8000`

```
Username: admin
Password: fitzrovia2024
```

### Running Individual Scrapers via CLI

```bash
python run_scraper.py --building "Parker"
python run_scraper.py --building "Story of Midtown"
python run_scraper.py --building "The Selby"
python run_scraper.py --building "eCentral"
python run_scraper.py --building "The Whitney"
python run_scraper.py --building "The Hampton"
python run_scraper.py --building "E18HTEEN"
python run_scraper.py --building "Corner on Broadway"
python run_scraper.py --building "Akoya Living"
python run_scraper.py --building "The Montgomery"
```

---

## Deployment

The platform runs on **Railway** using a Docker image built from Microsoft's official Playwright Python base, which bundles all Chromium system dependencies.

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN playwright install chromium

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Railway injects `PORT` at runtime. Deployments trigger automatically on every push to `main`.

---

## API Reference

| Method | Route | Auth | Description |
|---|---|---|---|
| `GET` | `/` | ✅ | Dashboard overview |
| `GET` | `/login` | — | Login page |
| `POST` | `/login` | — | Authenticate, issue JWT cookie |
| `GET` | `/logout` | — | Clear session |
| `GET` | `/buildings/{id}` | ✅ | Building detail view |
| `POST` | `/scrape` | ✅ | Trigger full scrape (all 10 buildings) |
| `POST` | `/scrape/building/{id}` | ✅ | Trigger single-building scrape |
| `GET` | `/scrape/status` | ✅ | Poll whether a scrape is currently running |
| `GET` | `/export/pdf` | ✅ | Generate and download the PDF report |

---

## Database Schema

### `buildings`
Seeded at startup. One row per tracked property.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `name` | TEXT | Building name |
| `address` | TEXT | Street address |
| `url` | TEXT | Source URL for scraping |
| `last_scraped_at` | DATETIME | Timestamp of most recent successful scrape |
| `scrape_status` | TEXT | `success`, `empty`, or `error` |
| `incentives` | TEXT | Latest incentive text extracted from homepage |

### `unit_listings`
One row per available unit per scrape run.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `building_id` | INTEGER | FK → buildings |
| `unit_number` | TEXT | Unit identifier (e.g. `2303`) |
| `unit_type` | TEXT | `Bachelor`, `1-Bed`, `2-Bed`, `3-Bed` |
| `bedrooms` | INTEGER | Bedroom count |
| `bathrooms` | FLOAT | Bathroom count |
| `floor_plan_name` | TEXT | Floor plan label (e.g. `Oriole`) |
| `sq_ft` | INTEGER | Square footage |
| `floor` | INTEGER | Floor number (where available) |
| `monthly_rent` | FLOAT | Listed monthly rent |
| `rent_min` / `rent_max` | FLOAT | Range where provided |
| `available_date` | TEXT | Availability date or `Available Now` |
| `incentives` | TEXT | Unit-level incentive (if separate from building) |
| `source_url` | TEXT | Direct URL of the scraped page |

### `scrape_runs`
Audit log of every scrape trigger.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `started_at` | DATETIME | Scrape start time |
| `completed_at` | DATETIME | Scrape end time |
| `status` | TEXT | `running`, `complete`, `error` |
| `buildings_scraped` | INTEGER | Count of buildings attempted |
| `units_found` | INTEGER | Total units saved |
| `errors` | TEXT | Semicolon-separated error messages |

---

## Known Issues

### The Montgomery — Cloudflare Bot Protection

The Montgomery's site (RentCafe/Yardi CMS) is protected by Cloudflare Turnstile. Railway operates from an AWS data center IP which Cloudflare identifies as a non-residential origin and serves a JS challenge page instead of real content.

The data structure is fully confirmed — each floor plan detail page (`/floorplans/oriole`, `/floorplans/maxwell`, etc.) contains server-rendered apartment cards with unit number, availability date, and price. The HTML parsing logic is correct and verified. The sole blocker is Cloudflare detecting the headless browser fingerprint at the network level.

Approaches tested: stealth JS injection, browser session warming via pre-navigation, `page.evaluate(fetch())` with Cloudflare session cookies, direct RentCafe API calls, and various httpx header configurations. All blocked.

**Production fix:** A residential proxy service (Bright Data, Oxylabs) or the `undetected-playwright` library would bypass Cloudflare's IP-based fingerprinting.

### Safe Module Imports

`scraper/buildings/__init__.py` uses `importlib.import_module` inside try/except blocks for each scraper. This ensures that a syntax error or import-time crash in any one scraper file does not prevent the remaining 9 from loading, since all scrapers share a single Python module namespace. Each failure is logged individually with the full exception.

---

## Credentials

| Field | Value |
|---|---|
| Dashboard login | `admin` / `fitzrovia2024` |
| Live URL | `https://web-production-10bb7.up.railway.app` |
| Auth mechanism | JWT (HS256), 8-hour expiry, stored in `HttpOnly` cookie |

---

*Fitzrovia Real Estate — Internal Use Only*
