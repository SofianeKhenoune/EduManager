from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import db
from app.models import Course, Department, Employee, Enrollment, Position, Role, Site, Student, Teacher, User
from app.seed import seed_initial_data


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


def _optional_int(value: str):
    if value in (None, ""):
        return None
    return int(value)


def _parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _ensure_role_id(role_name: str) -> int:
    role = Role.query.filter_by(name=role_name).first()
    if role is None:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.flush()
    return role.id


def _create_user(first_name: str, last_name: str, email: str, password: str, role_name: str):
    existing = User.query.filter_by(email=email).first()
    if existing is not None:
        return None, "Un utilisateur avec cette adresse e-mail existe déjà."

    role_id = _ensure_role_id(role_name)
    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=generate_password_hash(password),
        role_id=role_id,
    )
    db.session.add(user)
    db.session.flush()
    return user, None


@main_bp.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@main_bp.route("/api/kpis")
def api_kpis():
    data = {
        "students": Student.query.count(),
        "teachers": Teacher.query.count(),
        "courses": Course.query.count(),
        "employees": Employee.query.count(),
        "active_enrollments": Enrollment.query.filter_by(status="active").count(),
    }
    return jsonify(data), 200


@main_bp.route("/students", methods=["GET", "POST"])
def students_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            street = request.form.get("street", "").strip()
            city = request.form.get("city", "").strip()
            zip_code = request.form.get("zip_code", "").strip()
            birth_date = request.form.get("birth_date", "").strip()
            site_id = _optional_int(request.form.get("site_id"))

            if not all([first_name, last_name, email, password, street, city, zip_code, birth_date]):
                flash("Tous les champs obligatoires de l'élève doivent être renseignés.", "warning")
                return redirect(url_for("main.students_page"))

            user, error = _create_user(first_name, last_name, email, password, "student")
            if error:
                db.session.rollback()
                flash(error, "warning")
                return redirect(url_for("main.students_page"))

            student = Student(
                user_id=user.id,
                site_id=site_id,
                street=street,
                city=city,
                zip_code=zip_code,
                birth_date=_parse_date(birth_date),
                lives_alone=False,
            )
            db.session.add(student)
            db.session.commit()
            flash("Élève ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'élève. Vérifiez les données saisies.", "danger")

        return redirect(url_for("main.students_page"))

    students = Student.query.join(User, Student.user_id == User.id).order_by(User.last_name.asc()).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template("students.html", students=students, sites=sites)


@main_bp.route("/teachers", methods=["GET", "POST"])
def teachers_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            subject = request.form.get("subject", "").strip()

            if not all([first_name, last_name, email, password]):
                flash("Les champs prénom, nom, adresse e-mail et mot de passe sont obligatoires.", "warning")
                return redirect(url_for("main.teachers_page"))

            user, error = _create_user(first_name, last_name, email, password, "teacher")
            if error:
                db.session.rollback()
                flash(error, "warning")
                return redirect(url_for("main.teachers_page"))

            teacher = Teacher(user_id=user.id, subject=subject or None)
            db.session.add(teacher)
            db.session.commit()
            flash("Enseignant ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'enseignant.", "danger")

        return redirect(url_for("main.teachers_page"))

    teachers = Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()).all()
    return render_template("teachers.html", teachers=teachers)


@main_bp.route("/employees", methods=["GET", "POST"])
def employees_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            hire_date = request.form.get("hire_date", "").strip()
            employee_code = request.form.get("employee_code", "").strip()
            position_id = _optional_int(request.form.get("position_id"))
            department_id = _optional_int(request.form.get("department_id"))

            if not all([first_name, last_name, email, password, hire_date, employee_code]):
                flash("Des champs obligatoires de l'employé sont manquants.", "warning")
                return redirect(url_for("main.employees_page"))
            
            # Valider le format du matricule (nombre entier)
            if not employee_code.isdigit():
                flash("Le matricule doit être un nombre entier.", "warning")
                return redirect(url_for("main.employees_page"))
            
            # Formater en 5 chiffres avec zéros devant
            employee_code = employee_code.zfill(5)
            
            # Vérifier l'unicité du matricule
            existing_employee = Employee.query.filter_by(employee_id=employee_code).first()
            if existing_employee:
                flash(f"Le matricule {employee_code} est déjà utilisé.", "warning")
                return redirect(url_for("main.employees_page"))

            user, error = _create_user(first_name, last_name, email, password, "staff")
            if error:
                db.session.rollback()
                flash(error, "warning")
                return redirect(url_for("main.employees_page"))

            employee = Employee(
                user_id=user.id,
                hire_date=_parse_date(hire_date),
                employee_id=employee_code,
                position_id=position_id,
                department_id=department_id,
            )
            db.session.add(employee)
            db.session.commit()
            flash("Employé ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'employé. Vérifiez le matricule et la date d'embauche.", "danger")

        return redirect(url_for("main.employees_page"))

    employees = Employee.query.join(User, Employee.user_id == User.id).order_by(User.last_name.asc()).all()
    positions = Position.query.order_by(Position.title.asc()).all()
    departments = Department.query.order_by(Department.name.asc()).all()
    return render_template(
        "employees.html",
        employees=employees,
        positions=positions,
        departments=departments,
    )


@main_bp.route("/courses", methods=["GET", "POST"])
def courses_page():
    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            teacher_id = _optional_int(request.form.get("teacher_id"))
            site_id = _optional_int(request.form.get("site_id"))
            level = request.form.get("level", "").strip() or None
            day = request.form.get("day", "").strip() or None
            time_slot = request.form.get("time_slot", "").strip() or None
            start_hour = _optional_int(request.form.get("start_hour"))
            end_hour = _optional_int(request.form.get("end_hour"))

            if not title or teacher_id is None:
                flash("Le titre du cours et l'enseignant sont obligatoires.", "warning")
                return redirect(url_for("main.courses_page"))

            course = Course(
                title=title,
                teacher_id=teacher_id,
                site_id=site_id,
                level=level,
                day=day,
                time_slot=time_slot,
                start_hour=start_hour,
                end_hour=end_hour,
            )
            db.session.add(course)
            db.session.commit()
            flash("Cours ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter le cours. Vérifiez les contraintes horaires.", "danger")

        return redirect(url_for("main.courses_page"))

    courses = Course.query.order_by(Course.id.desc()).all()
    teachers = Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template("courses.html", courses=courses, teachers=teachers, sites=sites)


@main_bp.route("/admin/bootstrap", methods=["POST"])
def bootstrap_admin():
    if not current_app.config.get("ENABLE_BOOTSTRAP_ENDPOINT", False):
        return jsonify({"error": "not_found"}), 404

    expected_token = current_app.config.get("BOOTSTRAP_TOKEN", "")
    provided_token = request.headers.get("X-Bootstrap-Token", "")
    if not expected_token or provided_token != expected_token:
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    admin_email = payload.get("admin_email", "admin@edumanager.local")
    admin_password = payload.get("admin_password", "ChangeMe123!")
    admin_first_name = payload.get("admin_first_name", "Admin")
    admin_last_name = payload.get("admin_last_name", "EduManager")

    result = seed_initial_data(
        admin_email=admin_email,
        admin_password=admin_password,
        admin_first_name=admin_first_name,
        admin_last_name=admin_last_name,
    )
    return jsonify(result), 200
