import os

import click
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
migrate = Migrate()


def create_app() -> Flask:
    app = Flask(__name__)

    db_user = os.getenv("POSTGRES_USER", "user")
    db_password = os.getenv("POSTGRES_PASSWORD", "password")
    db_name = os.getenv("POSTGRES_DB", "EduManager")
    db_host = os.getenv("POSTGRES_HOST", "db")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    default_postgres_uri = (
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    app.config.from_mapping(
        SECRET_KEY="dev",
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", default_postgres_uri),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        ENABLE_BOOTSTRAP_ENDPOINT=os.getenv("ENABLE_BOOTSTRAP_ENDPOINT", "false").lower() in ("1", "true", "yes"),
        BOOTSTRAP_TOKEN=os.getenv("BOOTSTRAP_TOKEN", ""),
    )

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models
    from app.routes import main_bp
    from app.seed import seed_demo_data, seed_initial_data

    app.register_blueprint(main_bp)

    @app.cli.command("seed-initial")
    @click.option("--admin-email", default=lambda: os.getenv("ADMIN_EMAIL", "admin@edumanager.local"))
    @click.option("--admin-password", default=lambda: os.getenv("ADMIN_PASSWORD", "ChangeMe123!"))
    @click.option("--admin-first-name", default=lambda: os.getenv("ADMIN_FIRST_NAME", "Admin"))
    @click.option("--admin-last-name", default=lambda: os.getenv("ADMIN_LAST_NAME", "EduManager"))
    def seed_initial(admin_email: str, admin_password: str, admin_first_name: str, admin_last_name: str) -> None:
        result = seed_initial_data(
            admin_email=admin_email,
            admin_password=admin_password,
            admin_first_name=admin_first_name,
            admin_last_name=admin_last_name,
        )
        click.echo(
            "Seed completed: "
            f"roles_created={result['created_roles']}, "
            f"admin_created={result['admin_created']}, "
            f"admin_email={result['admin_email']}"
        )

    @app.cli.command("seed-demo")
    def seed_demo() -> None:
        result = seed_demo_data()
        click.echo(
            "Demo seed completed: "
            f"roles_created={result['roles_created']}, "
            f"site_created={result['site_created']}, "
            f"teacher_created={result['teacher_created']}, "
            f"student_created={result['student_created']}, "
            f"course_created={result['course_created']}, "
            f"enrollment_created={result['enrollment_created']}"
        )

    return app
