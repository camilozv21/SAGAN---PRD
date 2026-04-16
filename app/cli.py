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
