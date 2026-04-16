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

The app runs from a single Docker image that is identical to what Railway
builds. This removes per-OS native-library setup (WeasyPrint's pango/cairo
dependencies) and keeps local and production behavior in sync.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS)
  or Docker Engine + Compose plugin (Linux)

### Setup
```bash
# 1. Copy env template and fill in values
cp .env.example .env    # Windows: copy .env.example .env
# Edit .env — in particular generate bcrypt hashes for USER_CREDENTIALS.

# 2. Build and start the app
docker compose up --build
```

Visit `http://localhost:5000/health` to verify the server is up. The compose
setup runs `flask db-init` on start and uses `flask --debug`, so code edits
hot-reload inside the container. The SQLite DB lives in the named volume
`portal-data` and survives `docker compose down`.

### Tests
Run pytest inside the container:
```bash
docker compose run --rm web pytest
```

Or, if you prefer a venv for quick pure-Python feedback (tests that hit
WeasyPrint will skip without the GTK libs):
```bash
python -m venv venv && venv/Scripts/activate   # Windows
pip install -r requirements.txt
pytest
```

## Deploying to Railway

1. Create a new Railway project from this repository.
2. Railway detects the `Dockerfile` (via `railway.toml`) and builds the same
   image you use locally — no additional system deps needed.
3. Add a persistent volume named `portal-data` mounted at `/data` (already
   declared in `railway.toml`).
4. Configure these environment variables in the Railway dashboard:
   - `FLASK_ENV=production`
   - `SECRET_KEY` (long random string)
   - `USER_CREDENTIALS` (JSON: `{"user": "<bcrypt-hash>", ...}`)
   - `DATABASE_PATH=/data/portal.db` (already set in `railway.toml`)
5. Deploy. Railway uses the `startCommand` from `railway.toml`
   (`flask db-init && gunicorn 'app:create_app()'`) and health-checks `/health`.

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
Dockerfile             Image used both locally (compose) and on Railway
docker-compose.yml     Local dev orchestration (hot-reload, DB volume)
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
