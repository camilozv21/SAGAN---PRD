# AW Client Report Portal

Internal portal for EF — a financial planning firm — to enter client financial data and generate polished quarterly **SACS** (cashflow) and **TCC** (net worth) PDF reports in minutes instead of a full day.

## Stack

- **Backend**: Python + Flask
- **Frontend**: HTML + CSS + vanilla JavaScript (no frameworks)
- **Database**: SQLite (persisted on a Railway volume in production)
- **PDF generation**: WeasyPrint
- **Auth**: bcrypt-hashed credentials from env (3 internal users)
- **Hosting**: Railway

## Local Development

### Prerequisites
- Python 3.11+
- WeasyPrint system dependencies. On Windows follow the WeasyPrint install docs (GTK3 runtime); on macOS `brew install pango`; on Debian/Ubuntu `apt install libpango-1.0-0 libpangoft2-1.0-0`.

### Setup
```bash
# 1. Create a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env template and fill in values
cp .env.example .env    # Windows: copy .env.example .env
# Edit .env — in particular generate bcrypt hashes for USER_CREDENTIALS.

# 4. Run the app
flask --app wsgi run --debug
# Or:
python wsgi.py
```

Visit `http://localhost:5000/health` to verify the server is up.

### Tests
```bash
pytest
```

## Deploying to Railway

1. Create a new Railway project from this repository.
2. Railway auto-detects `requirements.txt` and `Procfile` via Nixpacks.
3. Add a persistent volume named `portal-data` mounted at `/data` (already declared in `railway.toml`).
4. Configure these environment variables in the Railway dashboard:
   - `FLASK_ENV=production`
   - `SECRET_KEY` (long random string)
   - `USER_CREDENTIALS` (JSON: `{"user": "<bcrypt-hash>", ...}`)
   - `DATABASE_PATH=/data/portal.db` (already set in `railway.toml`)
5. Deploy. Railway runs `gunicorn "app:create_app()"` and health-checks `/health`.

## Folder Structure

```
app/
  __init__.py          Flask app factory
  models/              SQLAlchemy models
  routes/              Blueprints by domain (clients, reports, auth)
  services/            Business logic (calculations, report assembly)
  pdf/                 WeasyPrint templates + PDF generation
  static/
    css/               Stylesheets (main.css with brand variables)
    js/                Vanilla JS modules (one per feature)
    img/               Static images / icons
  templates/
    base/              Base layout
    clients/           Client management views
    reports/           Report entry + preview views
config.py              Config classes (Dev / Prod)
wsgi.py                Entry point for gunicorn / `flask run`
Procfile               Railway start command
railway.toml           Railway deploy config + volume mount
requirements.txt
.env.example           Template for local .env

docs/
  references/          Sample SACS/TCC PDFs + data point list screenshots
  phases/              Phase plans & deliverables (see docs/phases/README.md)

tests/                 pytest suite
migrations/            Schema migrations (added once models exist)
```

## Project Context

See [CLAUDE.md](CLAUDE.md) for the full context guide: business rules, calculation formulas, PDF layout specs, and what is explicitly out of scope for V1.
