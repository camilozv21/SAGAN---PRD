import click
from flask.cli import with_appcontext


def register_cli(app):
    @app.cli.command("db-init")
    @with_appcontext
    def db_init_command():
        """Crea todas las tablas y siembra Sample Client + admin."""
        from migrations.init_db import init_database

        summary = init_database()
        click.echo("Database initialized.")
        for key, value in summary.items():
            click.echo(f"  {key}: {value}")

    @app.cli.command("db-reset")
    @with_appcontext
    def db_reset_command():
        """DROP todas las tablas y vuelve a sembrar. Destructivo."""
        from app import db
        from migrations.init_db import init_database

        db.drop_all()
        click.echo("All tables dropped.")
        summary = init_database()
        click.echo("Database re-initialized.")
        for key, value in summary.items():
            click.echo(f"  {key}: {value}")
