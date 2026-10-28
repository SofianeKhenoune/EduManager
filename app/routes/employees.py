from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import ADMIN_ROLES, roles_required
from app.models import (
    Department,
    Employee,
    EmployeeLeaveRequest,
    PerformanceReview,
    Position,
    SalaryDetail,
    User,
)
from app.routes.helpers import create_user, optional_float, optional_int, paginate, parse_date

bp = Blueprint("employees", __name__)

@bp.route("/employees", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def employees_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            hire_date = request.form.get("hire_date", "").strip()
            employee_code = request.form.get("employee_code", "").strip()
            position_id = optional_int(request.form.get("position_id"))
            department_id = optional_int(request.form.get("department_id"))

            if not all([first_name, last_name, email, password, hire_date, employee_code]):
                flash("Des champs obligatoires de l'employé sont manquants.", "warning")
                return redirect(url_for("employees.employees_page"))

            if not employee_code.isdigit():
                flash("Le matricule doit être un nombre entier.", "warning")
                return redirect(url_for("employees.employees_page"))

            employee_code = employee_code.zfill(5)
            existing_employee = Employee.query.filter_by(employee_id=employee_code).first()
            if existing_employee:
                flash(f"Le matricule {employee_code} est déjà utilisé.", "warning")
                return redirect(url_for("employees.employees_page"))

            user, error = create_user(first_name, last_name, email, password, "staff")
            if error:
                db.session.rollback()
                flash(error, "warning")
                return redirect(url_for("employees.employees_page"))

            employee = Employee(
                user_id=user.id,
                hire_date=parse_date(hire_date),
                employee_id=employee_code,
                position_id=position_id,
                department_id=department_id,
            )
            db.session.add(employee)
            db.session.commit()
            flash("Employe ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'employé. Vérifiez le matricule et la date d'embauche.", "danger")

        return redirect(url_for("employees.employees_page"))

    employees_pagination = paginate(Employee.query.join(User, Employee.user_id == User.id).order_by(User.last_name.asc()))
    positions = Position.query.order_by(Position.title.asc()).all()
    departments = Department.query.order_by(Department.name.asc()).all()
    return render_template(
        "employees.html",
        employees=employees_pagination.items,
        employees_pagination=employees_pagination,
        positions=positions,
        departments=departments,
    )


@bp.route("/employees/<int:emp_id>", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def employee_detail(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if action == "salary":
                detail = SalaryDetail(
                    employee_id=employee.id,
                    contract_type=request.form.get("contract_type", "").strip() or (employee.contract_type or "CDI"),
                    hourly_rate=optional_float(request.form.get("hourly_rate")),
                    annual_salary=optional_float(request.form.get("annual_salary")),
                    benefits=request.form.get("benefits", "").strip() or None,
                    effective_date=parse_date(request.form.get("effective_date")) if request.form.get("effective_date") else date.today(),
                    notes=request.form.get("notes", "").strip() or None,
                )
                db.session.add(detail)
                flash("Historique salarial ajoute.", "success")
            elif action == "review":
                review = PerformanceReview(
                    employee_id=employee.id,
                    review_date=parse_date(request.form.get("review_date")),
                    rating=optional_int(request.form.get("rating")) or 1,
                    comments=request.form.get("comments", "").strip() or None,
                    goals=request.form.get("goals", "").strip() or None,
                )
                db.session.add(review)
                flash("Évaluation employee ajoutée.", "success")
            elif action == "leave":
                leave_request = EmployeeLeaveRequest(
                    employee_id=employee.id,
                    start_date=parse_date(request.form.get("start_date")),
                    end_date=parse_date(request.form.get("end_date")),
                    leave_type=request.form.get("leave_type", "").strip() or "Congé paye",
                    status=request.form.get("status", "pending").strip() or "pending",
                    comments=request.form.get("comments", "").strip() or None,
                )
                db.session.add(leave_request)
                flash("Demande de congé ajoutée.", "success")
            db.session.commit()
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'enregistrer cette mise à jour RH.", "danger")
        return redirect(url_for("employees.employee_detail", emp_id=emp_id))
    return render_template("employee_detail.html", employee=employee)


@bp.route("/employees/<int:emp_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
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
                    flash("Cette adresse e-mail est déjà utilisee.", "warning")
                    return redirect(url_for("employees.edit_employee", emp_id=emp_id))
                employee.user.email = email
            employee.user.phone_number = request.form.get("phone_number", "").strip() or None
            hire_date = request.form.get("hire_date", "").strip()
            if hire_date:
                employee.hire_date = parse_date(hire_date)
            employee.position_id = optional_int(request.form.get("position_id"))
            employee.department_id = optional_int(request.form.get("department_id"))
            employee.civility = request.form.get("civility", "").strip() or None
            employee.birth_name = request.form.get("birth_name", "").strip() or None
            birth_date = request.form.get("birth_date", "").strip()
            employee.birth_date = parse_date(birth_date) if birth_date else None
            employee.birth_place = request.form.get("birth_place", "").strip() or None
            employee.nationality = request.form.get("nationality", "").strip() or None
            employee.address = request.form.get("address", "").strip() or None
            employee.zip_code = request.form.get("zip_code", "").strip() or None
            employee.city = request.form.get("city", "").strip() or None
            employee.contract_type = request.form.get("contract_type", "").strip() or None
            trial_period_end = request.form.get("trial_period_end", "").strip()
            employee.trial_period_end = parse_date(trial_period_end) if trial_period_end else None
            contract_end_date = request.form.get("contract_end_date", "").strip()
            employee.contract_end_date = parse_date(contract_end_date) if contract_end_date else None
            employee.level = request.form.get("level", "").strip() or None
            employee.index_grade = request.form.get("index_grade", "").strip() or None
            employee.hours_per_week = optional_float(request.form.get("hours_per_week", "").strip())
            employee.hours_per_month = optional_float(request.form.get("hours_per_month", "").strip())
            employee.hourly_rate = optional_float(request.form.get("hourly_rate", "").strip())
            employee.monthly_salary = optional_float(request.form.get("monthly_salary", "").strip())
            employee.navigo_pass = request.form.get("navigo_pass") == "1"
            employee.pas_rate = optional_float(request.form.get("pas_rate", "").strip())
            db.session.commit()
            flash("Employe mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour. Vérifiez les données.", "danger")
        return redirect(url_for("employees.edit_employee", emp_id=emp_id))

    positions = Position.query.order_by(Position.title.asc()).all()
    departments = Department.query.order_by(Department.name.asc()).all()
    return render_template("edit_employee.html", employee=employee, positions=positions, departments=departments)


@bp.route("/employees/<int:emp_id>/leave/<int:leave_id>/status", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def update_leave_status(emp_id, leave_id):
    employee = Employee.query.get_or_404(emp_id)
    leave_request = EmployeeLeaveRequest.query.get_or_404(leave_id)
    if leave_request.employee_id != employee.id:
        abort(404)
    status = request.form.get("status", "pending").strip()
    if status not in ("pending", "approved", "rejected"):
        flash("Statut de congé invalide.", "warning")
    else:
        leave_request.status = status
        db.session.commit()
        flash("Statut du congé mis à jour.", "success")
    return redirect(url_for("employees.employee_detail", emp_id=emp_id))


@bp.route("/employees/<int:emp_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_employee(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    user = employee.user
    db.session.delete(employee)
    db.session.delete(user)
    db.session.commit()
    flash("Employe supprime.", "success")
    return redirect(url_for("employees.employees_page"))

@bp.route("/departments", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def departments_page():
    if request.method == "POST":
        department = Department(
            name=request.form.get("name", "").strip(),
            manager_id=optional_int(request.form.get("manager_id")),
        )
        db.session.add(department)
        try:
            db.session.commit()
            flash("Departement ajoute.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Impossible d'ajouter ce département.", "danger")
        return redirect(url_for("employees.departments_page"))
    departments_pagination = paginate(Department.query.order_by(Department.name.asc()))
    managers = Employee.query.join(User, Employee.user_id == User.id).order_by(User.last_name.asc()).all()
    return render_template(
        "departments.html",
        departments=departments_pagination.items,
        departments_pagination=departments_pagination,
        managers=managers,
    )


@bp.route("/departments/<int:department_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_department(department_id):
    department = Department.query.get_or_404(department_id)
    department.name = request.form.get("name", "").strip()
    department.manager_id = optional_int(request.form.get("manager_id"))
    try:
        db.session.commit()
        flash("Departement mis à jour.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Impossible de mettre a jour ce département.", "danger")
    return redirect(url_for("employees.departments_page"))


@bp.route("/departments/<int:department_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_department(department_id):
    department = Department.query.get_or_404(department_id)
    if department.employees:
        flash("Impossible de supprimer ce département : des employés y sont rattaches.", "warning")
    else:
        db.session.delete(department)
        db.session.commit()
        flash("Departement supprime.", "success")
    return redirect(url_for("employees.departments_page"))


@bp.route("/positions", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def positions_page():
    if request.method == "POST":
        position = Position(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip() or None,
        )
        db.session.add(position)
        try:
            db.session.commit()
            flash("Poste ajoute.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Impossible d'ajouter ce poste.", "danger")
        return redirect(url_for("employees.positions_page"))
    positions_pagination = paginate(Position.query.order_by(Position.title.asc()))
    return render_template("positions.html", positions=positions_pagination.items, positions_pagination=positions_pagination)


@bp.route("/positions/<int:position_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_position(position_id):
    position = Position.query.get_or_404(position_id)
    position.title = request.form.get("title", "").strip()
    position.description = request.form.get("description", "").strip() or None
    try:
        db.session.commit()
        flash("Poste mis à jour.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Impossible de mettre a jour ce poste.", "danger")
    return redirect(url_for("employees.positions_page"))


@bp.route("/positions/<int:position_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_position(position_id):
    position = Position.query.get_or_404(position_id)
    if position.employees:
        flash("Impossible de supprimer ce poste : des employés y sont rattaches.", "warning")
    else:
        db.session.delete(position)
        db.session.commit()
        flash("Poste supprime.", "success")
    return redirect(url_for("employees.positions_page"))

