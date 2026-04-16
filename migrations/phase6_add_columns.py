"""Phase 6 migration: add new columns to existing tables.

Adds:
- quarterly_reports.transfer_day_snapshot (INTEGER, nullable)
- quarterly_reports.liabilities_snapshot (TEXT, nullable)
- users.is_admin (BOOLEAN, default 0)
- audit_logs table (new)

Safe to run multiple times — checks for column/table existence first.
"""
from app import db


def _column_exists(table, column):
    """Check if a column exists in a SQLite table."""
    result = db.session.execute(
        db.text(f"PRAGMA table_info({table})")
    ).fetchall()
    return any(row[1] == column for row in result)


def _table_exists(table):
    result = db.session.execute(
        db.text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
        ),
        {"name": table},
    ).fetchone()
    return result is not None


def migrate():
    """Apply Phase 6 schema changes."""
    changes = []

    # --- quarterly_reports: transfer_day_snapshot ---
    if not _column_exists("quarterly_reports", "transfer_day_snapshot"):
        db.session.execute(db.text(
            "ALTER TABLE quarterly_reports ADD COLUMN transfer_day_snapshot INTEGER"
        ))
        changes.append("Added quarterly_reports.transfer_day_snapshot")

    # --- quarterly_reports: liabilities_snapshot ---
    if not _column_exists("quarterly_reports", "liabilities_snapshot"):
        db.session.execute(db.text(
            "ALTER TABLE quarterly_reports ADD COLUMN liabilities_snapshot TEXT"
        ))
        changes.append("Added quarterly_reports.liabilities_snapshot")

    # --- users: is_admin ---
    if not _column_exists("users", "is_admin"):
        db.session.execute(db.text(
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
        ))
        # Set existing admin user to is_admin=1
        db.session.execute(db.text(
            "UPDATE users SET is_admin = 1 WHERE email = 'admin@example.com'"
        ))
        changes.append("Added users.is_admin (set admin@example.com to admin)")

    # --- audit_logs table ---
    if not _table_exists("audit_logs"):
        db.session.execute(db.text("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                report_id INTEGER REFERENCES quarterly_reports(id) ON DELETE SET NULL,
                action VARCHAR(60) NOT NULL,
                detail VARCHAR(255),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        changes.append("Created audit_logs table")

    db.session.commit()
    return changes


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        changes = migrate()
        if changes:
            for c in changes:
                print(f"  [OK] {c}")
        else:
            print("  No changes needed — schema already up to date.")
