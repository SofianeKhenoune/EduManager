import os
from datetime import timedelta

import click
from flask import Flask, request, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


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
    debug_mode = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    template_auto_reload = os.getenv("TEMPLATES_AUTO_RELOAD", "").lower() in (
        "1",
        "true",
        "yes",
    ) or debug_mode

    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        if debug_mode:
            secret_key = "dev"
        else:
            raise RuntimeError("SECRET_KEY environment variable is required when FLASK_DEBUG is off.")

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", default_postgres_uri),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TEMPLATES_AUTO_RELOAD=template_auto_reload,
        ENABLE_BOOTSTRAP_ENDPOINT=os.getenv("ENABLE_BOOTSTRAP_ENDPOINT", "false").lower()
        in ("1", "true", "yes"),
        BOOTSTRAP_TOKEN=os.getenv("BOOTSTRAP_TOKEN", ""),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
        in ("1", "true", "yes"),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=None,
    )
    app.jinja_env.auto_reload = template_auto_reload

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
    login_manager.login_message_category = "warning"

    from app import models  # noqa: F401
    from app.routes import register_blueprints
    from app.seed import seed_demo_data, seed_initial_data

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    register_blueprints(app)

    @app.context_processor
    def inject_template_helpers():
        def can_access(*roles):
            return (
                current_user.is_authenticated
                and hasattr(current_user, "has_role")
                and current_user.has_role(*roles)
            )

        def home_endpoint() -> str:
            if not current_user.is_authenticated:
                return "auth.login"
            if current_user.has_role("parent"):
                return "families.families_page"
            if current_user.has_role("teacher"):
                return "teachers_portal.teacher_my_classes"
            if current_user.has_role("volunteer"):
                return "courses.planning_page"
            if current_user.has_role("student"):
                return "student_portal.student_home"
            return "dashboard.index"

        def home_url() -> str:
            return url_for(home_endpoint())

        def home_label() -> str:
            if not current_user.is_authenticated:
                return "Connexion"
            if current_user.has_role("parent"):
                return "Retour a mon espace famille"
            if current_user.has_role("teacher"):
                return "Retour a mon espace enseignant"
            if current_user.has_role("volunteer"):
                return "Retour a mon espace benevolat"
            if current_user.has_role("student"):
                return "Retour a mon espace etudiant"
            return "Retour au tableau de bord"

        def pagination_url(endpoint: str, page: int):
            args = request.args.to_dict(flat=True)
            args["page"] = page
            return url_for(endpoint, **args)

        return {
            "can_access": can_access,
            "home_endpoint": home_endpoint,
            "home_url": home_url,
            "home_label": home_label,
            "pagination_url": pagination_url,
        }

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

    @app.cli.command("import-employees")
    @click.argument("excel_path")
    def import_employees(excel_path: str) -> None:
        """Importe les employés depuis un fichier Excel."""
        from app.import_employees import import_employees_from_excel

        result = import_employees_from_excel(excel_path)
        click.echo(f"Import completed: imported={result['imported']}, skipped={result['skipped']}")
        if result["errors"]:
            click.echo("Erreurs :")
            for error in result["errors"]:
                click.echo(f"  - {error}")

    return app
