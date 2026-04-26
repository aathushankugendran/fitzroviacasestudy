# GitHub + Deployment Setup Guide

Follow these steps in order. Takes ~10 minutes.

---

## Step 1 — Local Setup

```bash
# Clone or download the project
cd fitzrovia-scraper

# Run the one-command setup script
bash setup.sh

# Test a single scraper first (takes ~30 seconds)
source venv/bin/activate
python run_scraper.py --building Parker

# Start the web server
uvicorn app:app --reload
# Open http://localhost:8000  →  admin / fitzrovia2024
```

---

## Step 2 — Push to GitHub

### 2a. Create the GitHub repo

1. Go to **github.com → New repository**
2. Name it: `fitzrovia-rental-intelligence`
3. Set to **Private** (contains your project work)
4. Do NOT initialize with README (you already have one)
5. Click **Create repository**

### 2b. Push your code

```bash
cd fitzrovia-scraper

# Initialize git
git init
git add .
git commit -m "feat: initial scraper and web dashboard"

# Connect to GitHub (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/fitzrovia-rental-intelligence.git
git branch -M main
git push -u origin main
```

✅ Your code is now on GitHub.

---

## Step 3 — Deploy a Live URL (Render — free tier)

Render is the easiest free host that supports Playwright + Python.

### 3a. Create a Render account
Go to **render.com** → Sign up (use GitHub login for easy integration)

### 3b. Create a new Web Service

1. Click **New → Web Service**
2. Connect your GitHub repo `fitzrovia-rental-intelligence`
3. Fill in:
   - **Name:** `fitzrovia-rental-intelligence`
   - **Runtime:** Python 3
   - **Build Command:**
     ```
     pip install -r requirements.txt && playwright install chromium && playwright install-deps chromium
     ```
   - **Start Command:**
     ```
     uvicorn app:app --host 0.0.0.0 --port $PORT
     ```

### 3c. Set environment variables

In Render dashboard → **Environment** tab, add:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | (generate: `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD_HASH` | `$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBpj1IjK8xG9Ee` |
| `TOKEN_EXPIRE_MINUTES` | `480` |

> **The default hash is for password `fitzrovia2024`.**
> To use a different password, run:
> ```python
> from passlib.context import CryptContext
> print(CryptContext(schemes=["bcrypt"]).hash("your-new-password"))
> ```

### 3d. Add persistent disk (for SQLite)

1. Render → your service → **Disks**
2. Add disk: mount at `/data`, 1 GB
3. In `database.py`, update `DATABASE_URL` to:
   ```python
   DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/fitzrovia.db")
   ```
   (Use `/data/` when the disk env var is set)

### 3e. Deploy

Click **Deploy**. First deploy takes ~3–5 minutes (Playwright download).

Your live URL will be: `https://fitzrovia-rental-intelligence.onrender.com`

---

## Step 4 — Verify Everything Works

1. **Login:** Visit your live URL → sign in with `admin / fitzrovia2024`
2. **Trigger a scrape:** Click "Run Scrape" button (takes 2–4 min on first run)
3. **Export PDF:** Click "Export PDF" after data loads
4. **Share the URL:** Send to Fitzrovia interviewers

---

## Changing Your Password

```python
# Run this locally to generate a new hash
from passlib.context import CryptContext
ctx = CryptContext(schemes=["bcrypt"])
print(ctx.hash("your-secure-password-here"))
```

Then update `ADMIN_PASSWORD_HASH` in your Render environment variables.

---

## Troubleshooting

**Playwright install fails on Render:**
Add to build command:
```
pip install -r requirements.txt && playwright install chromium --with-deps
```

**SQLite resets on redeploy:**
Render's free tier doesn't persist files between deploys without a disk.
Add the disk as described in Step 3d.

**Scrape returns no data for a building:**
That building's website may have updated its HTML structure.
Check `run_scraper.py --building [Name]` locally and inspect the output.
The text-pattern fallback should still catch rent prices from the page body.
