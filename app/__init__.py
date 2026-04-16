from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

from config import get_config

load_dotenv()

db = SQLAlchemy()


def create_app(config=None):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    cfg = config or get_config()
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = cfg.SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = cfg.SQLALCHEMY_TRACK_MODIFICATIONS
    app.config["USER_CREDENTIALS"] = cfg.USER_CREDENTIALS

    db_path = Path(cfg.DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/health/db")
    def health_db():
        db_file = Path(cfg.DATABASE_PATH)
        volume_dir = db_file.parent
        marker = volume_dir / "volume_probe.txt"
        now = datetime.now(timezone.utc).isoformat()

        previous = marker.read_text().strip() if marker.exists() else None
        marker.write_text(now)

        with app.app_context():
            sqlite_ok = db.session.execute(text("SELECT 1")).scalar() == 1

        return jsonify(
            {
                "status": "ok",
                "volume_dir": str(volume_dir),
                "volume_dir_writable": True,
                "marker_previous_value": previous,
                "marker_current_value": now,
                "sqlite_connected": sqlite_ok,
                "database_uri": app.config["SQLALCHEMY_DATABASE_URI"],
            }
        )

    return app
