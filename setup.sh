#!/usr/bin/env bash
# setup.sh — One-command local setup for Fitzrovia Rental Intelligence
# Usage: bash setup.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[setup]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $1"; }
err()  { echo -e "${RED}[error]${NC} $1"; exit 1; }

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║  Fitzrovia Rental Intelligence — Setup    ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

# ── 1. Check Python ─────────────────────────────────────────────────────────
log "Checking Python version…"
python3 --version >/dev/null 2>&1 || err "Python 3 not found. Install from python.org"
PY=$(python3 -c "import sys; print(sys.version_info[:2] >= (3,10))")
[ "$PY" = "True" ] || warn "Python 3.10+ recommended. You have $(python3 --version)"

# ── 2. Virtual environment ───────────────────────────────────────────────────
if [ ! -d "venv" ]; then
  log "Creating virtual environment…"
  python3 -m venv venv
fi
log "Activating virtual environment…"
source venv/bin/activate

# ── 3. Install Python deps ───────────────────────────────────────────────────
log "Installing Python dependencies…"
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ── 4. Install Playwright browsers ──────────────────────────────────────────
log "Installing Playwright Chromium browser…"
playwright install chromium

# ── 5. Create .env if missing ───────────────────────────────────────────────
if [ ! -f ".env" ]; then
  log "Creating .env from template…"
  cp .env.example .env
  # Generate a random secret key
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i.bak "s/change-me-to-a-random-64-char-string/$SECRET/" .env && rm -f .env.bak
  warn ".env created. Default login: admin / fitzrovia2024"
  warn "Change ADMIN_PASSWORD_HASH before deploying!"
fi

# ── 6. Init database ─────────────────────────────────────────────────────────
log "Initialising database…"
python3 -c "
from database import create_tables, SessionLocal, seed_buildings
create_tables()
db = SessionLocal()
seed_buildings(db)
db.close()
print('  Database ready with 10 buildings seeded.')
"

echo ""
echo "  ✅  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. (Optional) Run a test scrape first:"
echo "     source venv/bin/activate"
echo "     python run_scraper.py --building Parker"
echo ""
echo "  2. Start the web app:"
echo "     source venv/bin/activate"
echo "     uvicorn app:app --reload"
echo ""
echo "  3. Open http://localhost:8000"
echo "     Login: admin / fitzrovia2024"
echo ""
