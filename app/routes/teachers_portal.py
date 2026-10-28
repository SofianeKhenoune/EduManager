from collections import defaultdict
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import OFFICE_ROLES, PEDAGOGY_MUTATION_ROLES, PEDAGOGY_ROLES, roles_required
from app.models import Course, StudentAssessment
from app.routes.helpers import optional_float, optional_int, parse_date, teacher_can_mutate_course

bp = Blueprint("teachers_portal", __name__)

def get_teacher_or_403():
    """Return the Teacher linked to the current user, or abort 403."""
    teacher = current_user.teacher
    if teacher is None:
        abort(403)
    return teacher


@bp.route("/teacher/my-classes")
@login_required
@roles_required(*PEDAGOGY_ROLES)
def teacher_my_classes():
    if current_user.has_role("teacher"):
        teacher = get_teacher_or_403()
        courses = sorted(teacher.courses, key=lambda c: (c.day or "", c.start_hour or 0))
    else:
        courses = Course.query.order_by(Course.title.asc()).all()
    return render_template("teacher_my_classes.html", courses=courses)


@bp.route("/teacher/courses/<int:course_id>")
@login_required
@roles_required(*PEDAGOGY_ROLES)
def teacher_course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    if current_user.has_role("teacher"):
        teacher = get_teacher_or_403()
        if course.teacher_id != teacher.id:
            abort(403)

    active_enrollments = [e for e in course.enrollments if e.status == "active"]
    students = sorted([e.student for e in active_enrollments], key=lambda s: s.last_name)

    all_sessions = sorted(course.sessions, key=lambda s: s.session_date)
    completed_sessions = [s for s in all_sessions if s.status == "completed"]

    attendance_stats = {}
    for student in students:
        stats = {"present": 0, "absent": 0, "late": 0, "excused": 0, "total": len(completed_sessions)}
        for cs in completed_sessions:
            record = next((r for r in cs.attendance_records if r.student_id == student.id), None)
            if record:
                stats[record.status] = stats.get(record.status, 0) + 1
            else:
                stats["absent"] += 1
        stats["présence_pct"] = round((stats["present"] + stats["late"]) / stats["total"] * 100) if stats["total"] > 0 else None
        attendance_stats[student.id] = stats

    assessments = (
        StudentAssessment.query.filter_by(course_id=course_id)
        .order_by(StudentAssessment.assessment_date.desc())
        .all()
    )
    assessments_by_student = defaultdict(list)
    for a in assessments:
        assessments_by_student[a.student_id].append(a)

    assessment_categories = ["Contrôle continu", "Contrôle", "Comportement", "Participation", "Devoir"]
    return render_template(
        "teacher_course_detail.html",
        course=course,
        students=students,
        all_sessions=all_sessions,
        completed_sessions=completed_sessions,
        attendance_stats=attendance_stats,
        assessments_by_student=assessments_by_student,
        assessment_categories=assessment_categories,
        today=date.today(),
    )


@bp.route("/teacher/courses/<int:course_id>/assessment", methods=["POST"])
@login_required
@roles_required(*PEDAGOGY_MUTATION_ROLES)
def teacher_add_assessment(course_id):
    course = Course.query.get_or_404(course_id)
    if not teacher_can_mutate_course(course):
        abort(403)
    try:
        assessment = StudentAssessment(
            student_id=optional_int(request.form.get("student_id")),
            course_id=course_id,
            assessment_date=parse_date(request.form.get("assessment_date")) if request.form.get("assessment_date") else date.today(),
            category=request.form.get("category", "").strip() or "Contrôle continu",
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
    return redirect(url_for("teachers_portal.teacher_course_detail", course_id=course_id))


@bp.route("/teacher/courses/<int:course_id>/assessment/<int:assessment_id>/delete", methods=["POST"])
@login_required
@roles_required(*PEDAGOGY_MUTATION_ROLES)
def teacher_delete_assessment(course_id, assessment_id):
    course = Course.query.get_or_404(course_id)
    if not teacher_can_mutate_course(course):
        abort(403)
    assessment = StudentAssessment.query.get_or_404(assessment_id)
    db.session.delete(assessment)
    db.session.commit()
    flash("Évaluation supprimée.", "success")
    return redirect(url_for("teachers_portal.teacher_course_detail", course_id=course_id))

