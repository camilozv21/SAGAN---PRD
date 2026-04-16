#!/usr/bin/env python3
"""SQLite database backup utility.

Usage:
    python scripts/backup_db.py [--source /data/portal.db] [--dest /data/backups]

Creates a timestamped copy of the database file and removes backups older
than 30 days (configurable via --retention-days).

For Railway cron:
    python scripts/backup_db.py --source /data/portal.db --dest /data/backups
"""
import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


def backup(source: Path, dest_dir: Path, retention_days: int = 30) -> Path:
    """Copy source DB to dest_dir with a timestamp suffix. Return backup path."""
    if not source.exists():
        print(f"Error: source database not found: {source}", file=sys.stderr)
        sys.exit(1)

    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"portal_{timestamp}.db"
    backup_path = dest_dir / backup_name

    shutil.copy2(source, backup_path)
    print(f"Backup created: {backup_path} ({backup_path.stat().st_size:,} bytes)")

    # Clean up old backups
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for old_file in dest_dir.glob("portal_*.db"):
        if old_file == backup_path:
            continue
        try:
            # Parse timestamp from filename
            ts_str = old_file.stem.replace("portal_", "")
            file_time = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if file_time < cutoff:
                old_file.unlink()
                removed += 1
        except (ValueError, OSError):
            continue

    if removed:
        print(f"Removed {removed} backup(s) older than {retention_days} days.")

    return backup_path


def main():
    parser = argparse.ArgumentParser(description="Backup SQLite database.")
    parser.add_argument("--source", default="/data/portal.db",
                        help="Path to the source database file.")
    parser.add_argument("--dest", default="/data/backups",
                        help="Directory for backup files.")
    parser.add_argument("--retention-days", type=int, default=30,
                        help="Remove backups older than N days (default: 30).")
    args = parser.parse_args()

    backup(Path(args.source), Path(args.dest), args.retention_days)


if __name__ == "__main__":
    main()
