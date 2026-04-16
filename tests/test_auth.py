"""Authentication tests (Phase 7)."""
from app import db
from app.models import User


def test_login_page_renders(app):
    """GET /login returns the login form."""
    client = app.test_client()
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign In" in resp.data
    assert b"email" in resp.data


def test_login_with_valid_credentials(app):
    """POST /login with correct email/password redirects to clients."""
    client = app.test_client()
    resp = client.post("/login", data={
        "email": "test@example.com",
        "password": "testpass",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clients" in resp.headers["Location"]


def test_login_with_wrong_password(app):
    """POST /login with wrong password shows error."""
    client = app.test_client()
    resp = client.post("/login", data={
        "email": "test@example.com",
        "password": "wrongpass",
    })
    assert resp.status_code == 401
    assert b"Invalid email or password" in resp.data


def test_login_with_nonexistent_email(app):
    """POST /login with unknown email shows error."""
    client = app.test_client()
    resp = client.post("/login", data={
        "email": "nobody@example.com",
        "password": "testpass",
    })
    assert resp.status_code == 401
    assert b"Invalid email or password" in resp.data


def test_protected_route_redirects_to_login(app):
    """Unauthenticated access to /clients/ redirects to /login."""
    client = app.test_client()
    resp = client.get("/clients/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_health_endpoint_is_public(app):
    """GET /health does not require authentication."""
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_logout_redirects_to_login(http):
    """GET /logout logs out and redirects to /login."""
    resp = http.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_redirect_with_next(app):
    """After login, user is redirected to the originally requested page."""
    client = app.test_client()
    resp = client.post("/login?next=/clients/1", data={
        "email": "test@example.com",
        "password": "testpass",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clients/1" in resp.headers["Location"]


def test_already_logged_in_redirects_from_login(http):
    """Authenticated user visiting /login gets redirected to clients."""
    resp = http.get("/login", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clients" in resp.headers["Location"]


def test_create_user_cli(app):
    """The create-user CLI command creates a user with hashed password."""
    from click.testing import CliRunner

    runner = CliRunner()
    with app.app_context():
        result = runner.invoke(
            app.cli.commands["create-user"],
            ["--email", "new@example.com", "--name", "New User",
             "--password", "securepass123"],
            input=None,
        )
        assert result.exit_code == 0
        assert "User created" in result.output

        user = User.query.filter_by(email="new@example.com").first()
        assert user is not None
        assert user.name == "New User"
        assert user.check_password("securepass123") is True
        assert user.is_admin is False


def test_create_user_cli_duplicate(app):
    """create-user rejects duplicate email."""
    from click.testing import CliRunner

    runner = CliRunner()
    with app.app_context():
        result = runner.invoke(
            app.cli.commands["create-user"],
            ["--email", "test@example.com", "--name", "Dup",
             "--password", "pass123"],
        )
        assert result.exit_code == 1
        assert "already exists" in result.output
