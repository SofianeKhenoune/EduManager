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


def _optional_float(value: str):
    if value in (None, ""):
        return None
    return float(value)


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


@main_bp.route("/employees/<int:emp_id>/edit", methods=["GET", "POST"])
def edit_employee(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        try:
            employee.user.first_name = request.form.get("first_name", "").strip()
            employee.user.last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            if email != employee.user.email:
                existing = User.query.filter_by(email=email).first()
                if existing:
                    flash("Cette adresse e-mail est déjà utilisée.", "warning")
                    return redirect(url_for("main.edit_employee", emp_id=emp_id))
                employee.user.email = email
            employee.user.phone_number = request.form.get("phone_number", "").strip() or None
            hire_date = request.form.get("hire_date", "").strip()
            if hire_date:
                employee.hire_date = _parse_date(hire_date)
            employee.position_id = _optional_int(request.form.get("position_id"))
            employee.department_id = _optional_int(request.form.get("department_id"))
            employee.civility = request.form.get("civility", "").strip() or None
            employee.birth_name = request.form.get("birth_name", "").strip() or None
            birth_date = request.form.get("birth_date", "").strip()
            employee.birth_date = _parse_date(birth_date) if birth_date else None
            employee.birth_place = request.form.get("birth_place", "").strip() or None
            employee.nationality = request.form.get("nationality", "").strip() or None
            employee.address = request.form.get("address", "").strip() or None
            employee.zip_code = request.form.get("zip_code", "").strip() or None
            employee.city = request.form.get("city", "").strip() or None
            employee.contract_type = request.form.get("contract_type", "").strip() or None
            trial_period_end = request.form.get("trial_period_end", "").strip()
            employee.trial_period_end = _parse_date(trial_period_end) if trial_period_end else None
            employee.level = request.form.get("level", "").strip() or None
            employee.index_grade = request.form.get("index_grade", "").strip() or None
            employee.hours_per_week = _optional_float(request.form.get("hours_per_week", "").strip())
            employee.hours_per_month = _optional_float(request.form.get("hours_per_month", "").strip())
            employee.hourly_rate = _optional_float(request.form.get("hourly_rate", "").strip())
            employee.monthly_salary = _optional_float(request.form.get("monthly_salary", "").strip())
            employee.navigo_pass = request.form.get("navigo_pass") == "1"
            employee.pas_rate = _optional_float(request.form.get("pas_rate", "").strip())
            db.session.commit()
            flash("Employé mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour. Vérifiez les données.", "danger")
        return redirect(url_for("main.edit_employee", emp_id=emp_id))

    positions = Position.query.order_by(Position.title.asc()).all()
    departments = Department.query.order_by(Department.name.asc()).all()
    return render_template("edit_employee.html", employee=employee, positions=positions, departments=departments)


@main_bp.route("/employees/<int:emp_id>/delete", methods=["POST"])
def delete_employee(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    user = employee.user
    for record in list(employee.salary_details) + list(employee.performance_reviews) + list(employee.leave_requests):
        db.session.delete(record)
    db.session.delete(employee)
    db.session.delete(user)
    db.session.commit()
    flash("Employé supprimé.", "success")
    return redirect(url_for("main.employees_page"))


@main_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == "POST":
        try:
            student.user.first_name = request.form.get("first_name", "").strip()
            student.user.last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            if email != student.user.email:
                existing = User.query.filter_by(email=email).first()
                if existing:
                    flash("Cette adresse e-mail est déjà utilisée.", "warning")
                    return redirect(url_for("main.edit_student", student_id=student_id))
                student.user.email = email
            student.street = request.form.get("street", "").strip()
            student.city = request.form.get("city", "").strip()
            student.zip_code = request.form.get("zip_code", "").strip()
            birth_date = request.form.get("birth_date", "").strip()
            if birth_date:
                student.birth_date = _parse_date(birth_date)
            student.site_id = _optional_int(request.form.get("site_id"))
            db.session.commit()
            flash("Élève mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
        return redirect(url_for("main.edit_student", student_id=student_id))

    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template("edit_student.html", student=student, sites=sites)


@main_bp.route("/students/<int:student_id>/delete", methods=["POST"])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    user = student.user
    for enrollment in list(student.enrollments):
        db.session.delete(enrollment)
    for payment in list(student.payments):
        for installment in list(payment.installments):
            db.session.delete(installment)
        db.session.delete(payment)
    db.session.delete(student)
    db.session.delete(user)
    db.session.commit()
    flash("Élève supprimé.", "success")
    return redirect(url_for("main.students_page"))


@main_bp.route("/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
def edit_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    if request.method == "POST":
        try:
            teacher.user.first_name = request.form.get("first_name", "").strip()
            teacher.user.last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            if email != teacher.user.email:
                existing = User.query.filter_by(email=email).first()
                if existing:
                    flash("Cette adresse e-mail est déjà utilisée.", "warning")
                    return redirect(url_for("main.edit_teacher", teacher_id=teacher_id))
                teacher.user.email = email
            teacher.subject = request.form.get("subject", "").strip() or None
            db.session.commit()
            flash("Enseignant mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
        return redirect(url_for("main.edit_teacher", teacher_id=teacher_id))

    return render_template("edit_teacher.html", teacher=teacher)


@main_bp.route("/teachers/<int:teacher_id>/delete", methods=["POST"])
def delete_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    if teacher.courses:
        flash("Impossible de supprimer cet enseignant : il est affecté à des cours.", "warning")
        return redirect(url_for("main.teachers_page"))
    user = teacher.user
    db.session.delete(teacher)
    db.session.delete(user)
    db.session.commit()
    flash("Enseignant supprimé.", "success")
    return redirect(url_for("main.teachers_page"))


@main_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == "POST":
        try:
            course.title = request.form.get("title", "").strip()
            teacher_id = _optional_int(request.form.get("teacher_id"))
            if not teacher_id:
                flash("L'enseignant est obligatoire.", "warning")
                return redirect(url_for("main.edit_course", course_id=course_id))
            course.teacher_id = teacher_id
            course.site_id = _optional_int(request.form.get("site_id"))
            course.level = request.form.get("level", "").strip() or None
            course.day = request.form.get("day", "").strip() or None
            course.time_slot = request.form.get("time_slot", "").strip() or None
            course.start_hour = _optional_int(request.form.get("start_hour"))
            course.end_hour = _optional_int(request.form.get("end_hour"))
            db.session.commit()
            flash("Cours mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour. Vérifiez les contraintes horaires.", "danger")
        return redirect(url_for("main.edit_course", course_id=course_id))

    teachers = Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template("edit_course.html", course=course, teachers=teachers, sites=sites)


@main_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    for enrollment in list(course.enrollments):
        db.session.delete(enrollment)
    db.session.delete(course)
    db.session.commit()
    flash("Cours supprimé.", "success")
    return redirect(url_for("main.courses_page"))


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
