from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

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

    return app
