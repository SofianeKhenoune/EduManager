from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import OFFICE_ROLES, PEDAGOGY_MUTATION_ROLES, PEDAGOGY_ROLES, roles_required
from app.models import Course, Student, StudentAssessment
from app.routes.helpers import optional_float, optional_int, paginate, parse_date, teacher_can_mutate_course

bp = Blueprint("assessments", __name__)

@bp.route("/assessments", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def assessments_page():
    if request.method == "POST":
        if not current_user.has_role(*PEDAGOGY_MUTATION_ROLES):
            abort(403)
        course_id = optional_int(request.form.get("course_id"))
        course = Course.query.get(course_id) if course_id else None
        if course is None or not teacher_can_mutate_course(course):
            abort(403)
        try:
            assessment = StudentAssessment(
                student_id=optional_int(request.form.get("student_id")),
                course_id=course_id,
                assessment_date=parse_date(request.form.get("assessment_date")) if request.form.get("assessment_date") else date.today(),
                category=request.form.get("category", "").strip() or "Controle continu",
                score=optional_float(request.form.get("score")),
                max_score=optional_float(request.form.get("max_score")) or 20,
                appreciation=request.form.get("appreciation", "").strip() or None,
            )
            db.session.add(assessment)
            db.session.commit()
            flash("Évaluation enregistrée.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'enregistrer cette évaluation.", "danger")
        return redirect(url_for("assessments.assessments_page"))

    student_filter = optional_int(request.args.get("student_id"))
    assessments_query = StudentAssessment.query.join(Student).outerjoin(Course)
    teacher_courses = []
    if current_user.has_role("teacher"):
        teacher = current_user.teacher
        if teacher:
            teacher_course_ids = [c.id for c in teacher.courses]
            assessments_query = assessments_query.filter(StudentAssessment.course_id.in_(teacher_course_ids))
            teacher_courses = teacher.courses
    if student_filter:
        assessments_query = assessments_query.filter(StudentAssessment.student_id == student_filter)
    assessments_pagination = paginate(assessments_query.order_by(StudentAssessment.assessment_date.desc()))
    available_courses = teacher_courses if current_user.has_role("teacher") else Course.query.order_by(Course.title.asc()).all()
    # For teacher: only students enrolled in their courses
    if current_user.has_role("teacher") and teacher_courses:
        enrolled_ids = set()
        for c in teacher_courses:
            for e in c.enrollments:
                if e.status == "active":
                    enrolled_ids.add(e.student_id)
        available_students = Student.query.filter(Student.id.in_(enrolled_ids)).order_by(Student.last_name.asc()).all()
    else:
        available_students = Student.query.order_by(Student.last_name.asc()).all()
    return render_template(
        "assessments.html",
        assessments=assessments_pagination.items,
        assessments_pagination=assessments_pagination,
        students=available_students,
        courses=available_courses,
        selected_student_id=student_filter,
    )


@bp.route("/assessments/<int:assessment_id>/delete", methods=["POST"])
@login_required
@roles_required(*PEDAGOGY_MUTATION_ROLES)
def delete_assessment(assessment_id):
    assessment = StudentAssessment.query.get_or_404(assessment_id)
    course = assessment.course or (Course.query.get(assessment.course_id) if assessment.course_id else None)
    if course is None or not teacher_can_mutate_course(course):
        abort(403)
    db.session.delete(assessment)
    db.session.commit()
    flash("Évaluation supprimée.", "success")
    return redirect(url_for("assessments.assessments_page"))

