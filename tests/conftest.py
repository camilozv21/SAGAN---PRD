import pytest

from app import create_app, db
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = Config()
    cfg.DATABASE_PATH = str(tmp_path / "test.db")
    flask_app = create_app(cfg)
    flask_app.config["TESTING"] = True
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def session(app):
    return db.session


@pytest.fixture
def http(app):
    """Flask test client. Named `http` to avoid colliding with the Client model."""
    return app.test_client()
