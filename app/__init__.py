import logging
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import get_config

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()


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

    if ":memory:" not in cfg.SQLALCHEMY_DATABASE_URI:
        db_path = Path(cfg.DATABASE_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    # Flask-Login setup
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to access this page."
    login_manager.login_message_category = "error"
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    from app import models  # noqa: F401  (registers tables with SQLAlchemy)
    from app.cli import register_cli
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.clients import clients_bp
    from app.routes.reports import reports_bp

    register_cli(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(reports_bp)

    # Auth middleware: protect all routes except login, health, and static
    PUBLIC_ENDPOINTS = {"auth.login", "health", "static"}

    @app.before_request
    def _require_login():
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        return None

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/")
    def root():
        return redirect(url_for("clients.list_clients"))

    @app.route("/help")
    def help_page():
        return render_template("help/guide.html")

    # Error handlers
    @app.errorhandler(404)
    def _not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def _server_error(e):
        app.logger.error("500 error: %s", e)
        return render_template("errors/500.html"), 500

    # Structured logging
    _configure_logging(app)

    app.logger.info("AW Client Report Portal started (env=%s, db=%s)",
                     app.config.get("ENV", "?"), cfg.DATABASE_PATH)

    return app


def _configure_logging(app):
    """Set up structured Python logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    ))
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
