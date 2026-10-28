from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import OFFICE_ROLES, roles_required
from app.models import Family, Site, Student
from app.routes.helpers import (
    age_on_cutoff,
    default_school_year,
    optional_int,
    paginate,
    parse_date,
)

bp = Blueprint("students", __name__)

@bp.route("/students", methods=["GET", "POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def students_page():
    query = request.args.get("q", "").strip()

    def render_students_page():
        students_query = Student.query
        if query:
            like_query = f"%{query}%"
            students_query = students_query.filter(
                or_(
                    Student.first_name.ilike(like_query),
                    Student.last_name.ilike(like_query),
                )
            )

        students_pagination = paginate(students_query.order_by(Student.last_name.asc(), Student.first_name.asc()))
        sites = Site.query.order_by(Site.name.asc()).all()
        families = Family.query.order_by(Family.father_last_name.asc()).all()

        return render_template(
            "students.html",
            students=students_pagination.items,
            students_pagination=students_pagination,
            sites=sites,
            families=families,
            default_school_year=default_school_year(),
            search_query=query,
        )

    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            birth_date = request.form.get("birth_date", "").strip()
            site_id = optional_int(request.form.get("site_id"))
            gender = request.form.get("gender", "").strip() or None
            is_reinscription = request.form.get("is_reinscription") == "1"
            lives_alone = request.form.get("lives_alone") == "1"
            default_school_year = default_school_year()

            if not all([first_name, last_name, birth_date, gender]) or site_id is None:
                flash("Prénom, nom, date de naissance, genre et site sont obligatoires.", "warning")
                return render_students_page()

            parsed_birth = parse_date(birth_date)
            cutoff = date(date.today().year, 10, 1)
            age_on_cutoff = age_on_cutoff(parsed_birth, cutoff)
            force_underage = request.form.get("force_underage") == "1"
            if age_on_cutoff < 6 and not force_underage:
                flash("L'élève doit avoir au moins 6 ans au 1er octobre de l'année en cours.", "warning")
                return render_students_page()
            if age_on_cutoff < 6 and force_underage:
                flash("Inscription en dessous de l'âge recommandée (validation forcée).", "warning")

            family_id = optional_int(request.form.get("family_id"))
            if not family_id:
                tarif_type = request.form.get("tarif_type", "").strip()
                school_year = request.form.get("school_year", default_school_year).strip() or default_school_year
                father_first_name = request.form.get("father_first_name", "").strip()
                father_last_name = request.form.get("father_last_name", "").strip()
                father_phone = request.form.get("father_phone", "").strip()
                father_email = request.form.get("father_email", "").strip().lower()
                mother_first_name = request.form.get("mother_first_name", "").strip()
                mother_last_name = request.form.get("mother_last_name", "").strip()
                mother_phone = request.form.get("mother_phone", "").strip()
                mother_email = request.form.get("mother_email", "").strip().lower()
                address_number = optional_int(request.form.get("address_number"))
                street = request.form.get("street", "").strip()
                city = request.form.get("city", "").strip()
                zip_code = request.form.get("zip_code", "").strip()

                if not all([
                    tarif_type,
                    school_year,
                    father_first_name,
                    father_last_name,
                    mother_first_name,
                    mother_last_name,
                    street,
                    city,
                    zip_code,
                ]) or address_number is None:
                    flash("Pour une nouvelle famille, tarif, année scolaire, parents et adresse complète sont obligatoires.", "warning")
                    return render_students_page()

                if not (father_email or mother_email):
                    flash("Au moins un e-mail parent est obligatoire.", "warning")
                    return render_students_page()

                if not (father_phone or mother_phone):
                    flash("Au moins un numéro de téléphone parent est obligatoire.", "warning")
                    return render_students_page()

                family = Family(
                    school_year=school_year,
                    tarif_type=tarif_type,
                    father_first_name=father_first_name,
                    father_last_name=father_last_name,
                    father_phone=father_phone or None,
                    father_email=father_email or None,
                    mother_first_name=mother_first_name,
                    mother_last_name=mother_last_name,
                    mother_phone=mother_phone or None,
                    mother_email=mother_email or None,
                    address_number=address_number,
                    street=street,
                    city=city,
                    zip_code=zip_code,
                )
                db.session.add(family)
                db.session.flush()
                family_id = family.id

            student = Student(
                first_name=first_name,
                last_name=last_name,
                site_id=site_id,
                family_id=family_id,
                gender=gender,
                is_reinscription=is_reinscription,
                birth_date=parsed_birth,
                lives_alone=lives_alone,
            )
            db.session.add(student)
            db.session.commit()
            flash("Élève ajouté avec succès.", "success")
            return redirect(url_for("enrollments.enrollments_page", student_id=student.id, quick_flow=1))
        except ValueError as exc:
            db.session.rollback()
            flash(f"Impossible d'ajouter l'élève : {exc}", "danger")
        except IntegrityError as exc:
            db.session.rollback()
            raw_error = str(getattr(exc, "orig", exc))
            lower_error = raw_error.lower()

            if "check_student_gender" in lower_error:
                detail = "le genre doit être M ou F"
            elif "students.birth_date" in lower_error and "not null" in lower_error:
                detail = "la date de naissance est obligatoire"
            elif "students.first_name" in lower_error and "not null" in lower_error:
                detail = "le prénom est obligatoire"
            elif "students.last_name" in lower_error and "not null" in lower_error:
                detail = "le nom est obligatoire"
            elif "students.site_id" in lower_error and "foreign key" in lower_error:
                detail = "le site sélectionné est invalide"
            elif "students.family_id" in lower_error and "foreign key" in lower_error:
                detail = "la famille sélectionnée est invalide"
            else:
                detail = raw_error

            flash(f"Impossible d'ajouter l'élève : {detail}", "danger")
        return render_students_page()

    return render_students_page()


@bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == "POST":
        try:
            student.first_name = request.form.get("first_name", "").strip()
            student.last_name = request.form.get("last_name", "").strip()
            birth_date = request.form.get("birth_date", "").strip()
            if birth_date:
                student.birth_date = parse_date(birth_date)
            student.site_id = optional_int(request.form.get("site_id"))
            student.family_id = optional_int(request.form.get("family_id"))
            student.gender = request.form.get("gender", "").strip() or None
            student.is_reinscription = request.form.get("is_reinscription") == "1"
            student.lives_alone = request.form.get("lives_alone") == "1"
            db.session.commit()
            flash("Élève mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
        return redirect(url_for("students.edit_student", student_id=student_id))

    sites = Site.query.order_by(Site.name.asc()).all()
    families = Family.query.order_by(Family.id.asc()).all()
    return render_template("edit_student.html", student=student, sites=sites, families=families)


@bp.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    family = student.family
    family_id = family.id if family else None
    was_only_student_in_family = bool(family) and len(family.students) == 1
    was_active_student = any(enrollment.status == "active" for enrollment in student.enrollments)

    for enrollment in list(student.enrollments):
        db.session.delete(enrollment)
    for assessment in list(student.assessments):
        db.session.delete(assessment)
    for attendance in list(student.attendance_records):
        db.session.delete(attendance)
    db.session.delete(student)
    db.session.commit()
    flash("Élève supprime.", "success")

    if family_id and was_only_student_in_family and was_active_student:
        flash("Cette famille n'a plus d'élève actif. Vous pouvez supprimer la famille si besoin.", "warning")
        return redirect(url_for("families.family_detail", family_id=family_id, suggest_delete=1))

    return redirect(url_for("students.students_page"))

