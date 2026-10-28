import csv
import io

from flask import Blueprint, Response, abort
from flask_login import current_user, login_required

from app.authz import ADMIN_ROLES, OFFICE_ROLES, roles_required, student_access_allowed
from app.models import Employee, Family, Payment, Student, User
from app.routes.helpers import (
    ASSO_NAME,
    filename_token,
    get_pdf_preset,
    pdf_draw_header,
    render_pdf,
)
from datetime import date
from reportlab.lib.units import mm

bp = Blueprint("documents", __name__)

@bp.route("/exports/<string:dataset>.csv")
@login_required
@roles_required(*OFFICE_ROLES)
def export_csv(dataset):
    output = io.StringIO()
    writer = csv.writer(output)

    if dataset == "employees" and not current_user.has_role(*ADMIN_ROLES):
        abort(403)

    if dataset == "students":
        writer.writerow(["Nom", "Prénom", "Famille", "Site", "Naissance", "Reinscription"])
        for student in Student.query.order_by(Student.last_name.asc()).all():
            writer.writerow([
                student.last_name,
                student.first_name,
                student.family.display_name if student.family else "",
                student.site.name if student.site else "",
                student.birth_date.isoformat() if student.birth_date else "",
                "Oui" if student.is_reinscription else "Non",
            ])
    elif dataset == "employees":
        writer.writerow(["Matricule", "Nom", "Prénom", "Email", "Departement", "Poste"])
        for employee in Employee.query.join(User).order_by(User.last_name.asc()).all():
            writer.writerow([
                employee.employee_id,
                employee.user.last_name,
                employee.user.first_name,
                employee.user.email,
                employee.department.name if employee.department else "",
                employee.position.title if employee.position else "",
            ])
    elif dataset == "payments":
        writer.writerow(["Famille", "Date", "Montant", "Mode", "Reste"])
        for payment in Payment.query.order_by(Payment.payment_date.desc()).all():
            writer.writerow([
                payment.family.display_name if payment.family else "",
                payment.payment_date.isoformat() if payment.payment_date else "",
                float(payment.total_amount or 0),
                payment.method or "",
                payment.remaining_amount,
            ])
    else:
        abort(404)

    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename={dataset}.csv"
    return response

@bp.route("/documents/students/<int:student_id>/attestation.pdf")
@login_required
def student_certificate_pdf(student_id):
    student = Student.query.get_or_404(student_id)
    if not student_access_allowed(student):
        abort(403)

    preset_name, preset = get_pdf_preset()

    active_courses = [enrollment.course for enrollment in student.enrollments if enrollment.status == "active"]
    school_year = student.family.school_year if student.family and student.family.school_year else f"{date.today().year}-{date.today().year + 1}"
    level = next((course.level for course in active_courses if course and course.level), None) or "sans_niveau"

    def draw(pdf, width, height):
        margin = preset["margin_mm"] * mm
        issue_date_str = date.today().strftime("%d-%m-%Y")
        pdf.setTitle(f"Attestation d'inscription – {student.full_name}")
        y = pdf_draw_header(pdf, width, height, preset)

        y -= 6 * mm
        pdf.setFont("Helvetica-Bold", preset["title_size"])
        pdf.setFillColorRGB(*preset["brand_rgb"])
        pdf.drawString(margin, y, "Attestation d'inscription")
        pdf.setFillColorRGB(0, 0, 0)
        y -= 5 * mm
        pdf.setFont("Helvetica", preset["body_size"])
        pdf.setFillColorRGB(*preset["muted_rgb"])
        pdf.drawString(margin, y, f"Année scolaire {school_year}")
        pdf.setFillColorRGB(0, 0, 0)
        y -= 12 * mm

        cert_ref = f"ATT-{student.id:05d}-{date.today().strftime('%Y%m%d')}"
        birth_str = student.birth_date.strftime("%d-%m-%Y") if student.birth_date else "Non renseignée"
        gender_label = "Garçon" if student.gender == "M" else ("Fille" if student.gender == "F" else "Non renseigné")
        reinscription_label = "Oui" if student.is_reinscription else "Non"
        age_label = str(student.age) if student.age is not None else "N/A"
        site_address = student.site.address if student.site and student.site.address else "N/A"
        label_col = 60 * mm

        def info_row(label, value):
            nonlocal y
            pdf.setFont("Helvetica-Bold", preset["body_size"])
            pdf.drawString(margin, y, label)
            pdf.setFont("Helvetica", preset["body_size"])
            pdf.drawString(margin + label_col, y, str(value))
            y -= 8 * mm

        info_row("Référence :", cert_ref)
        info_row("Nom et prénom :", student.full_name)
        info_row("Date de naissance :", birth_str)
        info_row("Âge :", age_label)
        info_row("Genre :", gender_label)
        info_row("Réinscription :", reinscription_label)
        info_row("Famille :", student.family.display_name if student.family else "Non renseignée")
        info_row("Site :", student.site.name if student.site else "Non renseigné")
        info_row("Adresse du site :", site_address)
        info_row("Tarif :", (student.family.tarif_type or "").capitalize() if student.family else "—")
        info_row("Niveau principal :", level)
        info_row("Nombre de cours actifs :", len(active_courses))
        y -= 4 * mm

        pdf.setFont("Helvetica", preset["body_size"])
        pdf.setFillColorRGB(*preset["muted_rgb"])
        pdf.drawString(
            margin,
            y,
            "Nous certifions que l'élève ci-dessus est inscrit(e) dans notre établissement pour l'année en cours.",
        )
        pdf.setFillColorRGB(0, 0, 0)
        y -= 9 * mm

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(margin, y, "Cours inscrits")
        y -= 6 * mm
        if active_courses:
            col_w = [65 * mm, 25 * mm, 30 * mm, 30 * mm]
            headers = ["Cours", "Niveau", "Jour", "Horaire"]
            pdf.setFillColorRGB(*preset["brand_rgb"])
            pdf.rect(margin, y - 5 * mm, width - 2 * margin, 7 * mm, fill=1, stroke=0)
            pdf.setFillColorRGB(1, 1, 1)
            pdf.setFont("Helvetica-Bold", 9)
            x = margin + 2 * mm
            for i, h in enumerate(headers):
                pdf.drawString(x, y - 2 * mm, h)
                x += col_w[i]
            y -= 12 * mm
            pdf.setFillColorRGB(0, 0, 0)
            for idx, course in enumerate(active_courses):
                if idx % 2 == 0:
                    pdf.setFillColorRGB(0.95, 0.98, 0.96)
                    pdf.rect(margin, y - 3 * mm, width - 2 * margin, 6.5 * mm, fill=1, stroke=0)
                    pdf.setFillColorRGB(0, 0, 0)
                pdf.setFont("Helvetica", 9)
                horaire = f"{course.start_hour}h – {course.end_hour}h" if course.start_hour and course.end_hour else "—"
                vals = [course.title or "—", course.level or "—", (course.day or "—").capitalize(), horaire]
                x = margin + 2 * mm
                for i, v in enumerate(vals):
                    pdf.drawString(x, y, v)
                    x += col_w[i]
                y -= 7 * mm
        else:
            pdf.setFont("Helvetica-Oblique", 10)
            pdf.drawString(margin + 2 * mm, y, "Aucun cours actif")
            y -= 8 * mm

        y -= 12 * mm
        pdf.setFont("Helvetica", preset["body_size"])
        pdf.drawString(margin, y, f"Fait à Aubervilliers, le {issue_date_str}")
        pdf.setFont("Helvetica-Bold", preset["body_size"])
        pdf.drawString(width - margin - preset["signature_w_mm"] * mm, y, "Cachet et signature :")
        y -= 22 * mm
        pdf.rect(
            width - margin - preset["signature_w_mm"] * mm,
            y,
            preset["signature_w_mm"] * mm,
            preset["signature_h_mm"] * mm,
            stroke=1,
            fill=0,
        )

        pdf.setFont("Helvetica-Oblique", 8)
        pdf.setFillColorRGB(*preset["footer_rgb"])
        pdf.drawCentredString(
            width / 2,
            15 * mm,
            f"Document généré le {issue_date_str} – {ASSO_NAME} – style {preset_name}",
        )
        pdf.setFillColorRGB(0, 0, 0)

    filename = (
        f"{filename_token(student.last_name)}_"
        f"{filename_token(student.first_name)}_"
        f"{filename_token(school_year)}_"
        f"{filename_token(level)}.pdf"
    )
    return render_pdf(filename, draw)


# ── Teacher portal ────────────────────────────────────────────────────────────
