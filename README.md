# Fitzrovia Rental Intelligence

> Automated rental pricing tracker for 10 competitor buildings in Midtown Toronto.
> Built for the Fitzrovia asset management take-home case study.

**Live demo:** `https://your-app.onrender.com` · **Login:** `admin` / `fitzrovia2024`

---

# Fitzrovia Rental Intelligence Tool

A web scraper and dashboard that automatically collects rental pricing data
from 10 competitor apartment buildings in Midtown Toronto and displays it
in a clean, consolidated interface.

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Scraping | Playwright (Python) | Handles JS-rendered sites; all 10 buildings use React/custom JS |
| API detection | Playwright response interception | Captures XHR/JSON before DOM rendering for speed |
| Backend | FastAPI + SQLite | Simple, fast, single-file DB — no external services needed |
| Frontend | Jinja2 templates | Server-rendered, no build step, straightforward |
| Auth | JWT + bcrypt | Real session auth, not a placeholder |
| PDF export | ReportLab | Pure Python, no headless browser needed for exports |

## Buildings Targeted

| # | Building | Address | Website |
|---|---|---|---|
| 1 | Parker | 200 Redpath Ave | parkerlife.ca |
| 2 | Story of Midtown | 75 Broadway Ave | mystorymidtown.com |
| 3 | The Selby | 25 Selby St | triconliving.com |
| 4 | eCentral | 15 Roehampton Ave | ecentralliving.com |
| 5 | The Montgomery | 2388 Yonge St | themontgomery.ca |
| 6 | The Whitney | 71 Redpath Ave | thewhitneyonredpath.com |
| 7 | The Hampton | 101 Roehampton Ave | thehampton.ca |
| 8 | E18HTEEN | 18 Erskine Ave | myrental.ca |
| 9 | Corner on Broadway | 223 Redpath Ave | thecornerrentals.com |
| 10 | Akoya Living | 55 Broadway Ave | akoyaliving.ca |

## Project Structure

```
fitzrovia-scraper/
├── run_scraper.py          # CLI: run scrapers standalone
├── app.py                  # FastAPI web app
├── database.py             # SQLAlchemy models + seed data
├── requirements.txt
├── scraper/
│   ├── base.py             # BaseScraper + UnitData dataclass
│   ├── runner.py           # Async orchestrator (concurrent scraping)
│   └── buildings/          # One scraper per building
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
└── templates/              # Jinja2 HTML templates
```

## Scraping Strategy

Each scraper uses a **dual strategy**:

1. **API interception (preferred)**: Playwright intercepts XHR/fetch calls
   during page load. Many of these sites (Parker, eCentral) use Yardi/RentCafe
   under the hood and expose clean JSON endpoints.

2. **DOM fallback**: If no JSON API is detected, the scraper targets
   semantic HTML selectors (`.floorplan-card`, `.suite-item`, etc.)
   and falls back to regex extraction on raw page text.

The `BaseScraper.extract_incentives()` method scans page text for
common promo patterns ("X months free", "$1,000 move-in bonus", etc.)
and attaches them to all units found on that page.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright browsers
playwright install chromium

# 3. Create .env file
cp .env.example .env
# Edit .env to set SECRET_KEY and ADMIN credentials

# 4. Run the scraper (standalone)
python run_scraper.py              # All buildings
python run_scraper.py --building Parker  # Single building
python run_scraper.py --list       # List all scrapers

# 5. Start the web app
uvicorn app:app --reload
# Then open http://localhost:8000
```

## Known Limitations

1. **JavaScript rendering**: All 10 sites use JS-heavy frontends.
   Playwright handles this but scrapes take ~2–5 minutes for all buildings.
   
2. **Selector fragility**: DOM selectors may break if a building redesigns
   their site. The text-pattern fallback provides a safety net but may
   miss unit-level details.

3. **Rate limiting / bot detection**: Some sites may serve CAPTCHAs or
   block headless browsers. The scraper spoofs a realistic user agent
   and blocks tracking pixels to help. Sites that actively bot-detect
   (Cloudflare, etc.) may require manual intervention.

4. **Incentive parsing**: Incentives are extracted via regex from page text.
   Creative or unusual offer wording may not be captured.

5. **Availability gaps**: Some buildings only show floor plan starting prices,
   not specific available units. These are captured as floor plan rows,
   not individual unit listings.

## What I'd Build Next

- **Scheduled scraping** via `APScheduler` or a cron job (e.g., daily at 6 AM)
- **Price change alerts** via email when a building changes rates
- **Historical trend charts** showing rent movement over time per building/unit type
- **Proxy rotation** to handle bot detection on aggressive sites
- **A/B selector testing** to automatically detect and adapt to layout changes
- **Unit-level deduplication** using fingerprinting to track the same unit across runs
