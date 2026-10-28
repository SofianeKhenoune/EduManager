from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import ADMIN_ROLES, roles_required
from app.models import Employee, Teacher, User, Volunteer
from app.routes.helpers import create_user, paginate

bp = Blueprint("teachers_admin", __name__)

@bp.route("/teachers", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def teachers_page():
    if request.method == "POST":
        try:
            teacher_origin = request.form.get("teacher_origin", "").strip()
            employee_id = optional_int(request.form.get("employee_id"))
            volunteer_id = optional_int(request.form.get("volunteer_id"))
            subject = request.form.get("subject", "").strip()

            user = None
            if teacher_origin == "employee":
                employee = Employee.query.get(employee_id) if employee_id else None
                if employee is None:
                    flash("Veuillez sélectionner un salarié valide.", "warning")
                    return redirect(url_for("teachers_admin.teachers_page"))
                if employee.user.teacher is not None:
                    flash("Ce salarié est déjà enseignant.", "warning")
                    return redirect(url_for("teachers_admin.teachers_page"))
                user = employee.user
            elif teacher_origin == "volunteer":
                volunteer = Volunteer.query.get(volunteer_id) if volunteer_id else None
                if volunteer is None:
                    flash("Veuillez sélectionner un bénévole valide.", "warning")
                    return redirect(url_for("teachers_admin.teachers_page"))
                if volunteer.user.teacher is not None:
                    flash("Ce bénévole est déjà enseignant.", "warning")
                    return redirect(url_for("teachers_admin.teachers_page"))
                user = volunteer.user
            else:
                flash("Un enseignant doit être un salarié ou un bénévole existant.", "warning")
                return redirect(url_for("teachers_admin.teachers_page"))

            teacher = Teacher(user_id=user.id, subject=subject or None)
            db.session.add(teacher)
            db.session.commit()
            flash("Enseignant ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'enseignant.", "danger")

        return redirect(url_for("teachers_admin.teachers_page"))

    teachers_pagination = paginate(Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()))
    available_employees = (
        Employee.query.join(User, Employee.user_id == User.id)
        .outerjoin(Teacher, Teacher.user_id == User.id)
        .filter(Teacher.id.is_(None))
        .order_by(User.last_name.asc(), User.first_name.asc())
        .all()
    )
    available_volunteers = (
        Volunteer.query.join(User, Volunteer.user_id == User.id)
        .outerjoin(Teacher, Teacher.user_id == User.id)
        .filter(Teacher.id.is_(None))
        .order_by(User.last_name.asc(), User.first_name.asc())
        .all()
    )
    return render_template(
        "teachers.html",
        teachers=teachers_pagination.items,
        teachers_pagination=teachers_pagination,
        available_employees=available_employees,
        available_volunteers=available_volunteers,
    )


@bp.route("/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
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
                    flash("Cette adresse e-mail est déjà utilisee.", "warning")
                    return redirect(url_for("teachers_admin.edit_teacher", teacher_id=teacher_id))
                teacher.user.email = email
            teacher.subject = request.form.get("subject", "").strip() or None
            db.session.commit()
            flash("Enseignant mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
        return redirect(url_for("teachers_admin.edit_teacher", teacher_id=teacher_id))

    return render_template("edit_teacher.html", teacher=teacher)


@bp.route("/teachers/<int:teacher_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    if teacher.courses:
        flash("Impossible de supprimer cet enseignant : il est affecté a des cours.", "warning")
        return redirect(url_for("teachers_admin.teachers_page"))
    user = teacher.user
    db.session.delete(teacher)
    if user and user.employee is None and user.volunteer is None:
        db.session.delete(user)
    db.session.commit()
    flash("Enseignant supprime.", "success")
    return redirect(url_for("teachers_admin.teachers_page"))


@bp.route("/teachers/delete-all", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_all_teachers():
    teachers = Teacher.query.all()
    skipped = 0
    deleted = 0
    for teacher in teachers:
        if teacher.courses:
            skipped += 1
            continue
        user = teacher.user
        db.session.delete(teacher)
        if user and user.employee is None and user.volunteer is None:
            db.session.delete(user)
        deleted += 1
    db.session.commit()
    if skipped:
        flash(f"{deleted} enseignant(s) supprimé(s). {skipped} ignoré(s) car affecté(s) à des cours.", "warning")
    else:
        flash(f"{deleted} enseignant(s) supprimé(s).", "success")
    return redirect(url_for("teachers_admin.teachers_page"))


@bp.route("/volunteers", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def volunteers_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            skills = request.form.get("skills", "").strip()

            if not all([first_name, last_name, email, password]):
                flash("Les champs prenom, nom, adresse e-mail et mot de passe sont obligatoires.", "warning")
                return redirect(url_for("teachers_admin.volunteers_page"))

            user, error = create_user(first_name, last_name, email, password, "volunteer")
            if error:
                db.session.rollback()
                flash(error, "warning")
                return redirect(url_for("teachers_admin.volunteers_page"))

            volunteer = Volunteer(user_id=user.id, skills=skills or None)
            db.session.add(volunteer)
            db.session.commit()
            flash("Bénévole ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter le bénévole.", "danger")

        return redirect(url_for("teachers_admin.volunteers_page"))

    volunteers_pagination = paginate(Volunteer.query.join(User, Volunteer.user_id == User.id).order_by(User.last_name.asc()))
    return render_template("volunteers.html", volunteers=volunteers_pagination.items, volunteers_pagination=volunteers_pagination)


@bp.route("/volunteers/<int:volunteer_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_volunteer(volunteer_id):
    volunteer = Volunteer.query.get_or_404(volunteer_id)
    if request.method == "POST":
        try:
            volunteer.user.first_name = request.form.get("first_name", "").strip()
            volunteer.user.last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            if email != volunteer.user.email:
                existing = User.query.filter_by(email=email).first()
                if existing:
                    flash("Cette adresse e-mail est déjà utilisee.", "warning")
                    return redirect(url_for("teachers_admin.edit_volunteer", volunteer_id=volunteer_id))
                volunteer.user.email = email
            volunteer.skills = request.form.get("skills", "").strip() or None
            volunteer.availability = request.form.get("availability", "").strip() or None
            db.session.commit()
            flash("Bénévole mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
        return redirect(url_for("teachers_admin.edit_volunteer", volunteer_id=volunteer_id))

    return render_template("edit_volunteer.html", volunteer=volunteer)


@bp.route("/volunteers/<int:volunteer_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_volunteer(volunteer_id):
    volunteer = Volunteer.query.get_or_404(volunteer_id)
    if volunteer.courses:
        flash("Impossible de supprimer ce bénévole : il est affecté a des cours.", "warning")
        return redirect(url_for("teachers_admin.volunteers_page"))
    user = volunteer.user
    db.session.delete(volunteer)
    db.session.delete(user)
    db.session.commit()
    flash("Bénévole supprime.", "success")
    return redirect(url_for("teachers_admin.volunteers_page"))

