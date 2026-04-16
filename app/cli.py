import click
from flask.cli import with_appcontext


def _run_migrations():
    """Run all pending migrations. Safe to call multiple times."""
    from migrations.phase6_add_columns import migrate as phase6_migrate

    changes = phase6_migrate()
    return changes


def register_cli(app):
    @app.cli.command("db-init")
    @with_appcontext
    def db_init_command():
        """Create all tables and seed Sample Client + admin user."""
        from migrations.init_db import init_database

        summary = init_database()
        click.echo("Database initialized.")
        for key, value in summary.items():
            click.echo(f"  {key}: {value}")

    @app.cli.command("db-migrate")
    @with_appcontext
    def db_migrate_command():
        """Apply pending schema migrations (non-destructive)."""
        changes = _run_migrations()
        if changes:
            click.echo("Migrations applied:")
            for c in changes:
                click.echo(f"  {c}")
        else:
            click.echo("No changes needed — schema already up to date.")

    @app.cli.command("db-reset")
    @with_appcontext
    def db_reset_command():
        """DROP all tables and re-seed. Destructive."""
        from app import db
        from migrations.init_db import init_database

        db.drop_all()
        click.echo("All tables dropped.")
        summary = init_database()
        click.echo("Database re-initialized.")
        for key, value in summary.items():
            click.echo(f"  {key}: {value}")

    @app.cli.command("create-user")
    @click.option("--email", prompt=True, help="User email address.")
    @click.option("--name", prompt=True, help="Display name.")
    @click.option("--admin", is_flag=True, default=False, help="Grant admin role.")
    @click.option("--password", prompt=True, hide_input=True,
                  confirmation_prompt=True, help="User password.")
    @with_appcontext
    def create_user_command(email, name, admin, password):
        """Create a new portal user with a bcrypt-hashed password."""
        from app import db
        from app.models import User

        email = email.strip().lower()
        existing = User.query.filter_by(email=email).first()
        if existing:
            click.echo(f"Error: user with email '{email}' already exists.")
            raise SystemExit(1)

        user = User(email=email, name=name.strip(), is_admin=admin)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"User created: {user.name} <{user.email}> (admin={admin})")
