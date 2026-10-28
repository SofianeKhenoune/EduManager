from collections import defaultdict
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import ADMIN_ROLES, OFFICE_ROLES, PEDAGOGY_MUTATION_ROLES, PEDAGOGY_ROLES, roles_required
from app.models import AttendanceRecord, Course, CourseSession, Enrollment, Site, Teacher, User, Volunteer
from app.routes.helpers import TIME_SLOTS, WEEKDAY_ORDER, optional_int, paginate, parse_date, teacher_can_mutate_course

bp = Blueprint("courses", __name__)

@bp.route("/courses", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def courses_page():
    if request.method == "POST":
        if not current_user.has_role(*OFFICE_ROLES):
            abort(403)
        try:
            title = request.form.get("title", "").strip()
            teacher_id = optional_int(request.form.get("teacher_id"))
            site_id = optional_int(request.form.get("site_id"))
            level = request.form.get("level", "").strip() or None
            day = request.form.get("day", "").strip() or None
            time_slot = request.form.get("time_slot", "").strip() or None
            start_hour = optional_int(request.form.get("start_hour"))
            end_hour = optional_int(request.form.get("end_hour"))

            if not title or teacher_id is None:
                flash("Le titre du cours et l'enseignant sont obligatoires.", "warning")
                return redirect(url_for("courses.courses_page"))

            volunteer_id = optional_int(request.form.get("volunteer_id"))
            course = Course(
                title=title,
                description=request.form.get("description", "").strip() or None,
                teacher_id=teacher_id,
                volunteer_id=volunteer_id,
                site_id=site_id,
                level=level,
                day=day,
                time_slot=time_slot,
                start_hour=start_hour,
                end_hour=end_hour,
                room=request.form.get("room", "").strip() or None,
                capacity=optional_int(request.form.get("capacity")) or 20,
            )
            db.session.add(course)
            db.session.commit()
            flash("Cours ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter le cours. Vérifiez les contraintes horaires.", "danger")

        return redirect(url_for("courses.courses_page"))

    courses_query = Course.query
    if current_user.has_role("teacher"):
        teacher = current_user.teacher
        if teacher:
            courses_query = courses_query.filter(Course.teacher_id == teacher.id)
    courses_pagination = paginate(courses_query.order_by(Course.id.desc()))
    teachers = Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()).all()
    volunteers = Volunteer.query.join(User, Volunteer.user_id == User.id).order_by(User.last_name.asc()).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template(
        "courses.html",
        courses=courses_pagination.items,
        courses_pagination=courses_pagination,
        teachers=teachers,
        volunteers=volunteers,
        sites=sites,
    )


@bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == "POST":
        if not current_user.has_role(*OFFICE_ROLES):
            abort(403)
        try:
            course.title = request.form.get("title", "").strip()
            course.description = request.form.get("description", "").strip() or None
            teacher_id = optional_int(request.form.get("teacher_id"))
            if not teacher_id:
                flash("L'enseignant est obligatoire.", "warning")
                return redirect(url_for("courses.edit_course", course_id=course_id))
            course.teacher_id = teacher_id
            course.volunteer_id = optional_int(request.form.get("volunteer_id"))
            course.site_id = optional_int(request.form.get("site_id"))
            course.level = request.form.get("level", "").strip() or None
            course.day = request.form.get("day", "").strip() or None
            course.time_slot = request.form.get("time_slot", "").strip() or None
            course.start_hour = optional_int(request.form.get("start_hour"))
            course.end_hour = optional_int(request.form.get("end_hour"))
            course.room = request.form.get("room", "").strip() or None
            course.capacity = optional_int(request.form.get("capacity")) or 20
            db.session.commit()
            flash("Cours mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour. Vérifiez les contraintes horaires.", "danger")
        return redirect(url_for("courses.edit_course", course_id=course_id))

    teachers = Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()).all()
    volunteers = Volunteer.query.join(User, Volunteer.user_id == User.id).order_by(User.last_name.asc()).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template("edit_course.html", course=course, teachers=teachers, volunteers=volunteers, sites=sites)


@bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash("Cours supprime.", "success")
    return redirect(url_for("courses.courses_page"))


@bp.route("/courses/delete-all", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_all_courses():
    courses = Course.query.all()
    deleted = len(courses)
    for course in courses:
        db.session.delete(course)
    db.session.commit()
    flash(f"{deleted} cours supprimé(s).", "success")
    return redirect(url_for("courses.courses_page"))


@bp.route("/planning", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def planning_page():
    if request.method == "POST":
        if not current_user.has_role(*PEDAGOGY_MUTATION_ROLES):
            abort(403)
        course_id = optional_int(request.form.get("course_id"))
        course = Course.query.get(course_id) if course_id else None
        if course is None or not teacher_can_mutate_course(course):
            abort(403)
        try:
            session = CourseSession(
                course_id=course_id,
                session_date=parse_date(request.form.get("session_date")),
                topic=request.form.get("topic", "").strip() or None,
                notes=request.form.get("notes", "").strip() or None,
                status=request.form.get("status", "planned").strip() or "planned",
            )
            db.session.add(session)
            db.session.commit()
            flash("Séance planifiée.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible de planifier cette séance.", "danger")
        return redirect(url_for("courses.planning_page"))

    site_filter = optional_int(request.args.get("site_id"))
    courses_query = Course.query
    if site_filter:
        courses_query = courses_query.filter(Course.site_id == site_filter)
    if current_user.has_role("teacher"):
        teacher = current_user.teacher
        if teacher:
            courses_query = courses_query.filter(Course.teacher_id == teacher.id)
    courses = courses_query.order_by(Course.day.asc(), Course.start_hour.asc()).all()
    schedule = defaultdict(list)
    for course in courses:
        schedule[course.day or "non_planifie"].append(course)
    teacher_course_ids = {c.id for c in courses}
    sessions_query = CourseSession.query.join(Course).order_by(CourseSession.session_date.asc())
    if site_filter:
        sessions_query = sessions_query.filter(Course.site_id == site_filter)
    if current_user.has_role("teacher") and teacher_course_ids:
        sessions_query = sessions_query.filter(CourseSession.course_id.in_(teacher_course_ids))
    sessions = sessions_query.limit(20).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    all_courses_for_form = courses if current_user.has_role("teacher") else Course.query.order_by(Course.title.asc()).all()
    return render_template(
        "planning.html",
        schedule=schedule,
        weekday_order=WEEKDAY_ORDER,
        sessions=sessions,
        courses=all_courses_for_form,
        sites=sites,
        selected_site_id=site_filter,
    )


@bp.route("/attendance/sessions/<int:session_id>", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def session_detail(session_id):
    session = CourseSession.query.get_or_404(session_id)
    if current_user.has_role("teacher"):
        teacher = current_user.teacher
        if teacher is None or session.course.teacher_id != teacher.id:
            abort(403)
    if request.method == "POST":
        if not teacher_can_mutate_course(session.course):
            abort(403)
        try:
            session.topic = request.form.get("topic", "").strip() or None
            session.notes = request.form.get("notes", "").strip() or None
            session.status = request.form.get("session_status", "planned").strip() or "planned"
            for enrollment in session.course.enrollments:
                if enrollment.status != "active":
                    continue
                field_name = f"student_{enrollment.student_id}"
                record_status = request.form.get(field_name, "present").strip() or "present"
                comment = request.form.get(f"comment_{enrollment.student_id}", "").strip() or None
                record = AttendanceRecord.query.filter_by(session_id=session.id, student_id=enrollment.student_id).first()
                if record is None:
                    record = AttendanceRecord(session_id=session.id, student_id=enrollment.student_id)
                    db.session.add(record)
                record.status = record_status
                record.comment = comment
            db.session.commit()
            flash("Feuille de présence mise à jour.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Impossible d'enregistrer la feuille de présence.", "danger")
        return redirect(url_for("courses.session_detail", session_id=session_id))

    existing_records = {record.student_id: record for record in session.attendance_records}
    active_students = [enrollment.student for enrollment in session.course.enrollments if enrollment.status == "active"]
    return render_template(
        "attendance_session.html",
        session=session,
        active_students=active_students,
        existing_records=existing_records,
    )

