from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import OFFICE_ROLES, roles_required
from app.models import Course, Enrollment, Student
from app.routes.helpers import ensure_family_payment_target, optional_int, paginate

bp = Blueprint("enrollments", __name__)

@bp.route("/enrollments", methods=["GET", "POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def enrollments_page():
    selected_student_id = optional_int(request.args.get("student_id"))
    quick_flow = request.args.get("quick_flow") == "1"

    if request.method == "POST":
        student_id = optional_int(request.form.get("student_id"))
        course_id = optional_int(request.form.get("course_id"))
        status = request.form.get("status", "active").strip()
        quick_flow = request.form.get("quick_flow") == "1"

        if not student_id or not course_id:
            flash("Élève et cours sont obligatoires.", "warning")
            return redirect(url_for("enrollments.enrollments_page", student_id=student_id, quick_flow=1 if quick_flow else None))

        existing = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
        if existing:
            flash("Cet élève est déjà inscrit a ce cours.", "warning")
            return redirect(url_for("enrollments.enrollments_page", student_id=student_id, quick_flow=1 if quick_flow else None))

        enrollment = Enrollment(student_id=student_id, course_id=course_id, status=status)
        db.session.add(enrollment)
        db.session.commit()

        payment_action = None
        family_payment = None
        if status == "active":
            student = Student.query.get(student_id)
            family = student.family if student else None
            if family is not None:
                family_payment, payment_action = ensure_family_payment_target(family)
                db.session.commit()

        if quick_flow:
            student = Student.query.get(student_id)
            if student and student.family_id:
                if family_payment is not None:
                    flash("Inscription ajoutée. Configurez maintenant le paiement.", "success")
                    return redirect(url_for("payments.payment_quick_setup", payment_id=family_payment.id))
                flash("Inscription ajoutée. Passez maintenant au paiement.", "success")
                return redirect(url_for("payments.payments_page", family_id=student.family_id, quick_flow=1))

        if payment_action == "created":
            flash("Inscription ajoutée. Paiement créé automatiquement.", "success")
        elif payment_action == "updated":
            flash("Inscription ajoutée. Montant familial recalculé en tenant compte des sommes déjà réglées.", "success")
        else:
            flash("Inscription ajoutée.", "success")
        return redirect(url_for("enrollments.enrollments_page", student_id=student_id if quick_flow else None, quick_flow=1 if quick_flow else None))

    search = request.args.get("q", "").strip()
    query = Enrollment.query.join(Student).join(Course)
    if selected_student_id:
        query = query.filter(Enrollment.student_id == selected_student_id)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Course.title.ilike(like),
            )
        )
    enrollments_pagination = paginate(query.order_by(Student.last_name.asc()))
    students = Student.query.order_by(Student.last_name.asc()).all()
    courses = Course.query.order_by(Course.title.asc()).all()
    selected_student = Student.query.get(selected_student_id) if selected_student_id else None
    return render_template(
        "enrollments.html",
        enrollments=enrollments_pagination.items,
        enrollments_pagination=enrollments_pagination,
        students=students,
        courses=courses,
        search_query=search,
        selected_student_id=selected_student_id,
        selected_student=selected_student,
        quick_flow=quick_flow,
    )


@bp.route("/enrollments/<int:enrollment_id>/edit", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def edit_enrollment(enrollment_id):
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    new_status = request.form.get("status", "").strip()
    if new_status in ("active", "annulee", "en_attente"):
        enrollment.status = new_status
        db.session.commit()
        flash("Statut mis à jour.", "success")
    else:
        flash("Statut invalide.", "warning")
    return redirect(url_for("enrollments.enrollments_page"))


@bp.route("/enrollments/<int:enrollment_id>/delete", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def delete_enrollment(enrollment_id):
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    db.session.delete(enrollment)
    db.session.commit()
    flash("Inscription supprimée.", "success")
    return redirect(url_for("enrollments.enrollments_page"))

