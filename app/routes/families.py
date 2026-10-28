from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import db
from app.authz import ADMIN_ROLES, OFFICE_ROLES, PARENT_ROLES, family_access_allowed, roles_required
from app.models import AttendanceRecord, Family, Site, Student, StudentAssessment, TARIF_GRID, User
from app.routes.helpers import (
    age_on_cutoff,
    create_user,
    ensure_family_payment_target,
    optional_int,
    paginate,
    parse_date,
)

bp = Blueprint("families", __name__)

@bp.route("/families", methods=["GET", "POST"])
@login_required
def families_page():
    if not current_user.has_role(*OFFICE_ROLES, *PARENT_ROLES):
        abort(403)
    if request.method == "POST":
        if not current_user.has_role(*OFFICE_ROLES):
            abort(403)
        family = Family(
            school_year=request.form.get("school_year", "2025-2026").strip() or "2025-2026",
            tarif_type=request.form.get("tarif_type", "normal").strip(),
            father_first_name=request.form.get("father_first_name", "").strip() or None,
            father_last_name=request.form.get("father_last_name", "").strip() or None,
            father_phone=request.form.get("father_phone", "").strip() or None,
            father_email=request.form.get("father_email", "").strip().lower() or None,
            mother_first_name=request.form.get("mother_first_name", "").strip() or None,
            mother_last_name=request.form.get("mother_last_name", "").strip() or None,
            mother_phone=request.form.get("mother_phone", "").strip() or None,
            mother_email=request.form.get("mother_email", "").strip().lower() or None,
            address_number=optional_int(request.form.get("address_number")),
            street=request.form.get("street", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            zip_code=request.form.get("zip_code", "").strip() or None,
        )
        db.session.add(family)
        db.session.commit()
        flash("Famille créée.", "success")
        return redirect(url_for("families.family_detail", family_id=family.id))

    search = request.args.get("q", "").strip()
    query = Family.query
    if current_user.has_role(*PARENT_ROLES):
        query = query.filter(Family.user_id == current_user.id)
        if not search:
            parent_families = query.order_by(Family.father_last_name.asc()).all()
            if len(parent_families) == 1:
                return redirect(url_for("families.family_detail", family_id=parent_families[0].id))
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Family.father_last_name.ilike(like),
                Family.mother_last_name.ilike(like),
                Family.father_first_name.ilike(like),
                Family.city.ilike(like),
            )
        )
    families_pagination = paginate(query.order_by(Family.father_last_name.asc()))
    return render_template(
        "families.html",
        families=families_pagination.items,
        families_pagination=families_pagination,
        search_query=search,
    )


@bp.route("/families/<int:family_id>")
@login_required
def family_detail(family_id):
    family = Family.query.get_or_404(family_id)
    if not family_access_allowed(family):
        abort(403)
    suggest_delete = request.args.get("suggest_delete") == "1"
    students_without_family = Student.query.filter_by(family_id=None).order_by(Student.last_name.asc()).all() if current_user.has_role(*OFFICE_ROLES) else []
    sites = Site.query.order_by(Site.name.asc()).all()
    suggested = family.suggested_amount()
    assessments = StudentAssessment.query.join(Student).filter(Student.family_id == family.id).order_by(StudentAssessment.assessment_date.desc()).limit(8).all()
    attendance_records = AttendanceRecord.query.join(Student).filter(Student.family_id == family.id).order_by(AttendanceRecord.id.desc()).limit(8).all()
    return render_template(
        "family_detail.html",
        family=family,
        students_without_family=students_without_family,
        suggested=suggested,
        tarif_grid=TARIF_GRID,
        sites=sites,
        suggest_delete=suggest_delete,
        assessments=assessments,
        attendance_records=attendance_records,
    )


@bp.route("/families/<int:family_id>/edit", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def edit_family(family_id):
    family = Family.query.get_or_404(family_id)
    family.school_year = request.form.get("school_year", "2025-2026").strip() or "2025-2026"
    family.tarif_type = request.form.get("tarif_type", "normal").strip()
    family.father_first_name = request.form.get("father_first_name", "").strip() or None
    family.father_last_name = request.form.get("father_last_name", "").strip() or None
    family.father_phone = request.form.get("father_phone", "").strip() or None
    family.father_email = request.form.get("father_email", "").strip().lower() or None
    family.mother_first_name = request.form.get("mother_first_name", "").strip() or None
    family.mother_last_name = request.form.get("mother_last_name", "").strip() or None
    family.mother_phone = request.form.get("mother_phone", "").strip() or None
    family.mother_email = request.form.get("mother_email", "").strip().lower() or None
    family.address_number = optional_int(request.form.get("address_number"))
    family.street = request.form.get("street", "").strip() or None
    family.city = request.form.get("city", "").strip() or None
    family.zip_code = request.form.get("zip_code", "").strip() or None
    db.session.commit()
    flash("Famille mise à jour.", "success")
    return redirect(url_for("families.family_detail", family_id=family_id))


@bp.route("/families/<int:family_id>/students/add", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def family_add_student(family_id):
    family = Family.query.get_or_404(family_id)
    student_id = optional_int(request.form.get("student_id"))
    if not student_id:
        flash("Sélectionnez un élève.", "warning")
        return redirect(url_for("families.family_detail", family_id=family_id))
    student = Student.query.get_or_404(student_id)
    student.family_id = family.id
    if any(enrollment.status == "active" for enrollment in student.enrollments):
        ensure_family_payment_target(family)
    db.session.commit()
    flash(f"{student.first_name} {student.last_name} ajoute(e) a la famille.", "success")
    return redirect(url_for("families.family_detail", family_id=family_id))


@bp.route("/families/<int:family_id>/students/new", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def family_new_student(family_id):
    family = Family.query.get_or_404(family_id)
    try:
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        birth_date = request.form.get("birth_date", "").strip()
        site_id = optional_int(request.form.get("site_id"))
        gender = request.form.get("gender", "").strip() or None
        is_reinscription = request.form.get("is_reinscription") == "1"

        if not all([first_name, last_name, birth_date]):
            flash("Prénom, nom et date de naissance sont obligatoires.", "warning")
            return redirect(url_for("families.family_detail", family_id=family_id))

        parsed_birth = parse_date(birth_date)
        cutoff = date(date.today().year, 10, 1)
        if age_on_cutoff(parsed_birth, cutoff) < 6:
            flash("L'élève doit avoir au moins 6 ans au 1er octobre de l'année en cours.", "warning")
            return redirect(url_for("families.family_detail", family_id=family_id))

        student = Student(
            first_name=first_name,
            last_name=last_name,
            site_id=site_id,
            family_id=family.id,
            gender=gender,
            is_reinscription=is_reinscription,
            birth_date=parsed_birth,
            lives_alone=False,
        )
        db.session.add(student)
        db.session.commit()
        flash(f"{first_name} {last_name} ajoute(e) a {family.display_name}.", "success")
    except (ValueError, IntegrityError):
        db.session.rollback()
        flash("Impossible d'ajouter l'élève. Vérifiez les données saisies.", "danger")
    return redirect(url_for("families.family_detail", family_id=family_id))


@bp.route("/families/<int:family_id>/students/<int:student_id>/remove", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def family_remove_student(family_id, student_id):
    student = Student.query.get_or_404(student_id)
    family = Family.query.get_or_404(family_id)
    student.family_id = None
    db.session.flush()
    ensure_family_payment_target(family)
    db.session.commit()
    flash("Élève retire de la famille.", "success")
    return redirect(url_for("families.family_detail", family_id=family_id))


@bp.route("/families/<int:family_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_family(family_id):
    family = Family.query.get_or_404(family_id)
    has_active_students = any(
        enrollment.status == "active"
        for student in family.students
        for enrollment in student.enrollments
    )
    if has_active_students:
        flash("Impossible de supprimer cette famille : au moins un élève est encore inscrit en actif.", "warning")
        return redirect(url_for("families.family_detail", family_id=family_id))

    for student in family.students:
        student.family_id = None

    for payment in family.payments:
        payment.family_id = None

    db.session.delete(family)
    db.session.commit()
    flash("Famille supprimée.", "success")
    return redirect(url_for("families.families_page"))


@bp.route("/families/<int:family_id>/set-parent", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def family_set_parent(family_id):
    family = Family.query.get_or_404(family_id)
    action = request.form.get("action", "create")

    if action == "remove":
        if family.user:
            user = family.user
            family.user_id = None
            db.session.flush()
            db.session.delete(user)
            db.session.commit()
            flash("Compte parent supprime.", "success")
        return redirect(url_for("families.family_detail", family_id=family_id))

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()

    if not all([first_name, last_name, email, password]):
        flash("Prénom, nom, email et mot de passe sont obligatoires.", "warning")
        return redirect(url_for("families.family_detail", family_id=family_id))

    if family.user:
        user = family.user
        user.first_name = first_name
        user.last_name = last_name
        if email != user.email:
            if User.query.filter_by(email=email).first():
                flash("Cette adresse e-mail est déjà utilisee.", "warning")
                return redirect(url_for("families.family_detail", family_id=family_id))
            user.email = email
        if password:
            user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash("Compte parent mis à jour.", "success")
    else:
        user, error = create_user(first_name, last_name, email, password, "parent")
        if error:
            db.session.rollback()
            flash(error, "warning")
            return redirect(url_for("families.family_detail", family_id=family_id))
        family.user_id = user.id
        db.session.commit()
        flash(f"Compte parent créé pour {first_name} {last_name}.", "success")

    return redirect(url_for("families.family_detail", family_id=family_id))

