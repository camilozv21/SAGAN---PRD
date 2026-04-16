from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import get_config

load_dotenv()

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


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

    if ":memory:" not in cfg.SQLALCHEMY_DATABASE_URI:
        db_path = Path(cfg.DATABASE_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    from app import models  # noqa: F401  (registers tables with SQLAlchemy)
    from app.cli import register_cli
    from app.routes.admin import admin_bp
    from app.routes.clients import clients_bp
    from app.routes.reports import reports_bp

    register_cli(app)
    app.register_blueprint(admin_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(reports_bp)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/")
    def root():
        return redirect(url_for("clients.list_clients"))

    return app
