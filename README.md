# AW Client Report Portal

Internal portal for EF — a financial planning firm — to enter client financial data and generate polished quarterly **SACS** (cashflow) and **TCC** (net worth) PDF reports in minutes instead of a full day.

## Stack

- **Backend**: Python + Flask
- **Frontend**: HTML + CSS + vanilla JavaScript (no frameworks)
- **Database**: SQLite (persisted on a Railway volume in production)
- **PDF generation**: WeasyPrint
- **Auth**: Flask-Login + bcrypt (users managed via CLI)
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
# 1. Copy env template
cp .env.example .env    # Windows: copy .env.example .env

# 2. Build and start the app
docker compose up --build
```

Visit `http://localhost:5000/health` to verify the server is up.

### Creating Users
Users are managed via the Flask CLI (not hardcoded):
```bash
# Inside the container or with your venv activated:
flask create-user --email andrew@firm.com --name "Andrew"
flask create-user --email rebecca@firm.com --name "Rebecca"
flask create-user --email maryann@firm.com --name "Maryann"
# Each command prompts for a password interactively.

# To grant admin (audit log access):
flask create-user --email andrew@firm.com --name "Andrew" --admin
```

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
   - `SECRET_KEY` (long random string — `python -c "import secrets; print(secrets.token_hex(32))"`)
   - `DATABASE_PATH=/data/portal.db` (already set in `railway.toml`)
5. Deploy. The Dockerfile CMD runs `flask db-init && gunicorn ...` and
   health-checks `/health`.
6. After first deploy, create users:
   ```bash
   railway run flask create-user --email andrew@firm.com --name "Andrew" --admin
   railway run flask create-user --email rebecca@firm.com --name "Rebecca"
   railway run flask create-user --email maryann@firm.com --name "Maryann"
   ```

## Database Backups

```bash
# Run manually or via cron:
python scripts/backup_db.py --source /data/portal.db --dest /data/backups

# Options:
#   --retention-days 30  (default: remove backups older than 30 days)
```

## Folder Structure

```
app/
  __init__.py          Flask app factory + auth middleware
  models/              SQLAlchemy models
  routes/              Blueprints: auth, clients, reports, admin
  services/            Business logic (calculations, PDF generation)
  pdf/templates/       WeasyPrint HTML templates for SACS/TCC PDFs
  static/
    css/               Stylesheets (main.css with brand variables)
    js/                Vanilla JS modules (one per feature)
  templates/
    auth/              Login page
    base/              Base layout
    clients/           Client CRUD views
    reports/           Report entry + detail views
    errors/            404, 500 error pages
    help/              User guide
config.py              Config classes (Dev / Prod)
wsgi.py                Entry point for gunicorn / flask run
scripts/
  backup_db.py         SQLite backup with retention cleanup
Dockerfile             Image used both locally and on Railway
docker-compose.yml     Local dev (hot-reload, DB volume)
railway.toml           Railway deploy config + volume mount
requirements.txt
.env.example

tests/                 pytest suite (calculations, auth, PDF, integration)
migrations/            Schema migrations
```

## Project Context

See [CLAUDE.md](CLAUDE.md) for the full context guide: business rules, calculation formulas, PDF layout specs, and what is explicitly out of scope for V1.
