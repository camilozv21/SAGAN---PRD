import pytest

from app import create_app, db
from app.models import User
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = Config()
    cfg.DATABASE_PATH = str(tmp_path / "test.db")
    flask_app = create_app(cfg)
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["LOGIN_DISABLED"] = True
    with flask_app.app_context():
        db.create_all()
        # Create a default test user for auth context
        user = User(email="test@example.com", name="Test User", is_admin=True)
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def session(app):
    return db.session


@pytest.fixture
def http(app):
    """Flask test client. Named `http` to avoid colliding with the Client model.

    Automatically logs in as the test user so protected routes are accessible.
    """
    client = app.test_client()
    # Log in via the auth endpoint
    client.post("/login", data={
        "email": "test@example.com",
        "password": "testpass",
    })
    return client
