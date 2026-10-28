from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.authz import ADMIN_ROLES, OFFICE_ROLES, PARENT_ROLES, family_access_allowed, roles_required
from app.models import Family, Payment, PaymentInstallment
from app.routes.helpers import (
    ASSO_NAME,
    family_remaining_amount,
    filename_token,
    get_pdf_preset,
    next_due_date,
    optional_float,
    optional_int,
    paginate,
    parse_date,
    pdf_draw_header,
    render_pdf,
)
from reportlab.lib.units import mm

bp = Blueprint("payments", __name__)

@bp.route("/payments", methods=["GET", "POST"])
@login_required
def payments_page():
    if not current_user.has_role(*OFFICE_ROLES, *PARENT_ROLES):
        abort(403)

    selected_family_id = optional_int(request.args.get("family_id"))
    quick_flow = request.args.get("quick_flow") == "1"

    if request.method == "POST":
        if not current_user.has_role(*OFFICE_ROLES):
            abort(403)
        family_id = optional_int(request.form.get("family_id"))
        creation_mode = request.form.get("creation_mode", "manual").strip().lower() or "manual"
        total_amount = optional_float(request.form.get("total_amount"))
        payment_date_raw = request.form.get("payment_date", "").strip()
        payment_date = parse_date(payment_date_raw) if payment_date_raw else None
        method_raw = request.form.get("method", "").strip()
        method = method_raw if method_raw in ("CB", "ESP", "CHQ") else None
        custom_method = request.form.get("custom_method", "").strip() or None
        installments_count = optional_int(request.form.get("installments_count"))
        quick_flow = request.form.get("quick_flow") == "1"

        if creation_mode not in ("auto", "manual"):
            creation_mode = "manual"

        family = Family.query.get(family_id) if family_id else None

        if family_id and total_amount is None:
            if family:
                total_amount = float(family.suggested_amount())

        if not family_id or total_amount is None:
            flash("Famille et montant sont obligatoires.", "warning")
            return redirect(url_for("payments.payments_page", family_id=family_id, quick_flow=1 if quick_flow else None))

        if family is None:
            flash("Famille introuvable.", "warning")
            return redirect(url_for("payments.payments_page", family_id=family_id, quick_flow=1 if quick_flow else None))

        if family.active_children_count <= 0:
            flash("Impossible de créer un paiement : cette famille n'a aucun enfant inscrit actif.", "warning")
            return redirect(url_for("payments.payments_page", family_id=family_id, quick_flow=1 if quick_flow else None))

        if creation_mode == "auto":
            remaining_amount = family_remaining_amount(family)
            if remaining_amount <= 0:
                flash("Cette famille est déjà soldée. Utilisez le mode Manuel pour un encaissement exceptionnel.", "warning")
                return redirect(url_for("payments.payments_page", family_id=family_id, quick_flow=1 if quick_flow else None))
            # Auto mode aligns the payment target with current outstanding balance.
            total_amount = remaining_amount

        if method is None and custom_method is None:
            flash("Sélectionnez un mode de paiement ou renseignez un mode personnalisé.", "warning")
            return redirect(url_for("payments.payments_page", family_id=family_id, quick_flow=1 if quick_flow else None))

        method_label = {
            "CB": "Carte bancaire",
            "ESP": "Espèces",
            "CHQ": "Chèque",
        }.get(method)
        if custom_method:
            method_label = custom_method

        payment = Payment(family_id=family_id, total_amount=total_amount, payment_date=payment_date, method=method)
        db.session.add(payment)

        if installments_count and installments_count > 0:
            installment_base = payment.payment_date or date.today()
            total_cents = int(round(float(total_amount) * 100))
            base_cents = total_cents // installments_count
            remainder = total_cents % installments_count
            previous_due = installment_base
            for idx in range(1, installments_count + 1):
                cents = base_cents + (1 if idx <= remainder else 0)
                due_date = next_due_date(previous_due, 1)
                db.session.add(
                    PaymentInstallment(
                        payment=payment,
                        installment_number=idx,
                        amount=round(cents / 100, 2),
                        payment_date=due_date,
                        method=method if idx == 1 else None,
                    )
                )
                previous_due = due_date

        db.session.commit()

        if quick_flow:
            flash("Paiement créé. Parcours d'inscription terminé.", "success")
            return redirect(url_for("families.family_detail", family_id=family_id))

        if method_label:
            flash(f"Paiement créé (mode: {method_label}).", "success")
        else:
            flash("Paiement créé.", "success")
        return redirect(url_for("payments.payment_detail", payment_id=payment.id))

    search = request.args.get("q", "").strip()
    query = Payment.query.join(Family, Payment.family_id == Family.id)
    if current_user.has_role(*PARENT_ROLES):
        query = query.filter(Family.user_id == current_user.id)
    if selected_family_id:
        query = query.filter(Payment.family_id == selected_family_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Family.father_last_name.ilike(like),
                Family.mother_last_name.ilike(like),
                Family.father_first_name.ilike(like),
            )
        )
    payments_pagination = paginate(query.order_by(Payment.payment_date.desc()))
    families = Family.query.order_by(Family.father_last_name.asc()).all() if current_user.has_role(*OFFICE_ROLES) else []
    family_remaining_by_id = {family.id: family_remaining_amount(family) for family in families}
    default_total_amount = None
    if selected_family_id:
        selected_family = next((family for family in families if family.id == selected_family_id), None)
        if selected_family:
            default_total_amount = float(selected_family.suggested_amount())
    selected_family_remaining = None
    if selected_family_id:
        selected_family_remaining = family_remaining_by_id.get(selected_family_id)

    return render_template(
        "payments.html",
        payments=payments_pagination.items,
        payments_pagination=payments_pagination,
        families=families,
        family_remaining_by_id=family_remaining_by_id,
        default_total_amount=default_total_amount,
        selected_family_remaining=selected_family_remaining,
        search_query=search,
        selected_family_id=selected_family_id,
        quick_flow=quick_flow,
    )


@bp.route("/payments/<int:payment_id>")
@login_required
def payment_detail(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if not family_access_allowed(payment.family):
        abort(403)
    today = date.today()
    locked_installment_ids = set()
    if not current_user.has_role("admin", "manager"):
        locked_installment_ids = {
            inst.id
            for inst in payment.installments
            if inst.id is not None and inst.payment_date is not None and inst.payment_date < today
        }
    return render_template(
        "payment_detail.html",
        payment=payment,
        today=today,
        locked_installment_ids=locked_installment_ids,
    )


@bp.route("/payment-setup/<int:payment_id>", methods=["GET", "POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def payment_quick_setup(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if request.method == "POST":
        family = payment.family
        if family is not None and family.active_children_count <= 0:
            flash("Impossible d'enregistrer ce paiement : cette famille n'a aucun enfant inscrit actif.", "warning")
            return redirect(url_for("payments.payment_detail", payment_id=payment_id))

        total_amount = optional_float(request.form.get("total_amount"))
        payment_date_raw = request.form.get("payment_date", "").strip()
        payment_date = parse_date(payment_date_raw) if payment_date_raw else date.today()
        installments_count = optional_int(request.form.get("installments_count")) or 1

        if total_amount is None:
            flash("Le montant total est obligatoire.", "warning")
            return redirect(url_for("payments.payment_quick_setup", payment_id=payment_id))

        payment.total_amount = total_amount
        payment.payment_date = payment_date

        # Remove existing installments
        for inst in list(payment.installments):
            db.session.delete(inst)
        db.session.flush()

        # Create installments
        total_cents = int(round(float(total_amount) * 100))
        base_cents = total_cents // installments_count
        remainder = total_cents % installments_count

        for idx in range(1, installments_count + 1):
            auto_cents = base_cents + (1 if idx <= remainder else 0)
            auto_amount = round(auto_cents / 100, 2)
            due_date = payment_date if idx == 1 else next_due_date(payment_date, idx - 1)

            custom_amount = optional_float(request.form.get(f"inst_{idx}_amount"))
            custom_date_raw = request.form.get(f"inst_{idx}_date", "").strip()
            custom_date = parse_date(custom_date_raw) if custom_date_raw else None
            inst_method = request.form.get(f"inst_{idx}_method") or None

            db.session.add(PaymentInstallment(
                payment=payment,
                installment_number=idx,
                amount=custom_amount if custom_amount is not None else auto_amount,
                payment_date=custom_date if custom_date else due_date,
                method=inst_method,
            ))

        db.session.commit()
        flash("Paiement configuré avec succès.", "success")
        return redirect(url_for("payments.payment_detail", payment_id=payment.id))

    default_amount = float(payment.total_amount or (payment.family.suggested_amount() if payment.family else 0))
    return render_template(
        "payment_setup.html",
        payment=payment,
        default_amount=default_amount,
    )


@bp.route("/payments/<int:payment_id>/installments", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def add_installment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    family = payment.family
    if family is not None and family.active_children_count <= 0:
        flash("Impossible d'enregistrer ce paiement : cette famille n'a aucun enfant inscrit actif.", "warning")
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))

    installment_number = optional_int(request.form.get("installment_number"))
    amount = optional_float(request.form.get("amount"))
    method = request.form.get("method", "").strip() or None
    payment_date_raw = request.form.get("payment_date", "").strip()
    payment_date = parse_date(payment_date_raw) if payment_date_raw else None
    if not installment_number or amount is None:
        flash("Numéro et montant de l'échéance sont obligatoires.", "warning")
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))
    paid_total = float(sum((i.amount or 0) for i in payment.installments if i.method))
    remaining = float(payment.total_amount or 0) - paid_total
    if method and amount > remaining + 0.01:
        flash("Montant trop élève: risque de trop-percu.", "warning")
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))
    existing = PaymentInstallment.query.filter_by(payment_id=payment_id, installment_number=installment_number).first()
    if existing:
        flash("Ce numero d'échéance existe déjà.", "warning")
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))
    installment = PaymentInstallment(
        payment_id=payment_id,
        installment_number=installment_number,
        amount=amount,
        method=method,
        payment_date=payment_date,
    )
    db.session.add(installment)
    db.session.commit()
    flash("Echeance ajoutée.", "success")
    return redirect(url_for("payments.payment_detail", payment_id=payment_id))


@bp.route("/payments/<int:payment_id>/installments/<int:installment_id>/edit", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def edit_installment(payment_id, installment_id):
    payment = Payment.query.get_or_404(payment_id)
    family = payment.family
    if family is not None and family.active_children_count <= 0:
        flash("Impossible d'enregistrer ce paiement : cette famille n'a aucun enfant inscrit actif.", "warning")
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))

    installment = PaymentInstallment.query.filter_by(id=installment_id, payment_id=payment_id).first_or_404()

    is_past_installment = installment.payment_date is not None and installment.payment_date < date.today()
    if is_past_installment and not current_user.has_role("admin", "manager"):
        flash(
            "Les échéances passées ne peuvent être modifiées que par un administrateur ou un manager.",
            "warning",
        )
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))

    new_amount = optional_float(request.form.get("amount"))
    new_method = request.form.get("method", "").strip() or None
    payment_date_raw = request.form.get("payment_date", "").strip()
    new_payment_date = parse_date(payment_date_raw) if payment_date_raw else installment.payment_date

    if new_amount is None:
        flash("Le montant est obligatoire.", "warning")
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))

    other_paid = float(sum((i.amount or 0) for i in payment.installments if i.id != installment.id and i.method))
    max_allowed = float(payment.total_amount or 0) - other_paid
    if new_method and new_amount > max_allowed + 0.01:
        flash("Montant invalide: trop-percu detecte.", "warning")
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))

    installment.amount = new_amount
    installment.method = new_method
    installment.payment_date = new_payment_date

    # Keep the edited installment amount and rebalance remaining forecast installments.
    all_installments = sorted(payment.installments, key=lambda i: i.installment_number or 0)
    total_cents = int(round(float(payment.total_amount or 0) * 100))
    fixed_total_cents = 0
    floating_installments = []

    for inst in all_installments:
        inst_cents = int(round(float(inst.amount or 0) * 100))
        if inst.id == installment.id or inst.method:
            fixed_total_cents += inst_cents
        else:
            floating_installments.append(inst)

    remaining_cents = max(total_cents - fixed_total_cents, 0)
    if floating_installments:
        base_cents = remaining_cents // len(floating_installments)
        remainder = remaining_cents % len(floating_installments)
        for idx, inst in enumerate(floating_installments):
            cents = base_cents + (1 if idx < remainder else 0)
            inst.amount = round(cents / 100, 2)

    db.session.commit()
    if floating_installments:
        flash("Echeance mise à jour. Les autres échéances prévisionnelles ont été recalculées.", "success")
    else:
        flash("Echeance mise à jour.", "success")
    return redirect(url_for("payments.payment_detail", payment_id=payment_id))


@bp.route("/payments/<int:payment_id>/installments/<int:installment_id>/delete", methods=["POST"])
@login_required
@roles_required(*OFFICE_ROLES)
def delete_installment(payment_id, installment_id):
    installment = PaymentInstallment.query.filter_by(id=installment_id, payment_id=payment_id).first_or_404()
    is_past_installment = installment.payment_date is not None and installment.payment_date < date.today()
    if is_past_installment and not current_user.has_role("admin", "manager"):
        flash(
            "Les échéances passées ne peuvent être supprimées que par un administrateur ou un manager.",
            "warning",
        )
        return redirect(url_for("payments.payment_detail", payment_id=payment_id))
    if installment.method and not current_user.has_role("admin", "manager"):
        abort(403)
    db.session.delete(installment)
    db.session.commit()
    flash("Echeance supprimée.", "success")
    return redirect(url_for("payments.payment_detail", payment_id=payment_id))


@bp.route("/payments/<int:payment_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    family = payment.family
    if family is not None:
        has_active_enrollment = any(
            enrollment.status == "active"
            for student in family.students
            for enrollment in student.enrollments
        )
        if has_active_enrollment:
            flash(
                "Suppression refusee: cette famille a des élèves inscrits en cours actif.",
                "warning",
            )
            return redirect(url_for("payments.payment_detail", payment_id=payment.id))

    db.session.delete(payment)
    db.session.commit()
    flash("Paiement supprime.", "success")
    return redirect(url_for("payments.payments_page"))

@bp.route("/documents/payments/<int:payment_id>.pdf")
@login_required
def payment_receipt_pdf(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if not family_access_allowed(payment.family):
        abort(403)

    preset_name, preset = get_pdf_preset()

    def draw(pdf, width, height):
        margin = preset["margin_mm"] * mm
        pdf.setTitle(f"Reçu de paiement – {payment.family.display_name if payment.family else ''}")
        y = pdf_draw_header(pdf, width, height, preset)

        y -= 6 * mm
        pdf.setFont("Helvetica-Bold", preset["title_size"])
        pdf.setFillColorRGB(*preset["brand_rgb"])
        pdf.drawString(margin, y, "Reçu de paiement")
        pdf.setFillColorRGB(0, 0, 0)
        y -= 12 * mm

        receipt_ref = f"REC-{payment.id:05d}-{date.today().strftime('%Y%m%d')}"
        family_name = payment.family.display_name if payment.family else "N/A"
        family_id_str = str(payment.family_id) if payment.family_id else "N/A"
        school_year = payment.family.school_year if payment.family and payment.family.school_year else "N/A"
        parent_phone = ""
        if payment.family:
            parent_phone = payment.family.father_phone or payment.family.mother_phone or ""
        parent_email = ""
        if payment.family:
            parent_email = payment.family.father_email or payment.family.mother_email or ""
        payment_date_str = payment.payment_date.strftime("%d-%m-%Y") if payment.payment_date else "Non renseignée"
        issue_date_str = date.today().strftime("%d-%m-%Y")
        installments = payment.installments
        label_col = 55 * mm
        method_labels = {"CB": "Carte bancaire", "ESP": "Espèces", "CHQ": "Chèque"}
        method_main = method_labels.get(payment.method, "Non renseigné") if payment.method else "Non renseigné"
        paid_status = "Soldé" if payment.remaining_amount <= 0 else "Partiellement réglé"

        def info_row(label, value, bold_value=False):
            nonlocal y
            pdf.setFont("Helvetica-Bold", preset["body_size"])
            pdf.drawString(margin, y, label)
            pdf.setFont("Helvetica-Bold" if bold_value else "Helvetica", preset["body_size"])
            pdf.drawString(margin + label_col, y, str(value))
            y -= 7 * mm

        info_row("Référence :", receipt_ref, bold_value=True)
        info_row("Famille :", family_name)
        info_row("Dossier famille :", family_id_str)
        info_row("Année scolaire :", school_year)
        info_row("Date du paiement :", payment_date_str)
        info_row("Date d'émission :", issue_date_str)
        info_row("Mode principal :", method_main)
        info_row("Statut :", paid_status)
        info_row("Montant total :", f"{float(payment.total_amount or 0):.2f} €", bold_value=True)
        info_row("Déjà réglé :", f"{payment.installments_total:.2f} €")
        info_row("Reste à régler :", f"{payment.remaining_amount:.2f} €", bold_value=True)
        if parent_phone:
            info_row("Téléphone parent :", parent_phone)
        if parent_email:
            info_row("Email parent :", parent_email)
        y -= 5 * mm

        pdf.setFont("Helvetica", preset["body_size"])
        pdf.setFillColorRGB(*preset["muted_rgb"])
        pdf.drawString(margin, y, "Ce document atteste les paiements enregistrés à ce jour.")
        pdf.setFillColorRGB(0, 0, 0)
        y -= 7 * mm

        if installments:
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(margin, y, "Détail des échéances")
            y -= 6 * mm
            col_w = [10 * mm, 35 * mm, 40 * mm, 40 * mm]
            headers = ["N°", "Montant", "Date", "Moyen de paiement"]
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
            for idx, inst in enumerate(sorted(installments, key=lambda i: i.installment_number)):
                if idx % 2 == 0:
                    pdf.setFillColorRGB(0.95, 0.98, 0.96)
                    pdf.rect(margin, y - 3 * mm, width - 2 * margin, 6.5 * mm, fill=1, stroke=0)
                    pdf.setFillColorRGB(0, 0, 0)
                pdf.setFont("Helvetica", 9)
                vals = [
                    str(inst.installment_number),
                    f"{float(inst.amount):.2f} €",
                    inst.payment_date.strftime("%d-%m-%Y") if inst.payment_date else "—",
                    method_labels.get(inst.method, "Prévision") if inst.method else "Prévision",
                ]
                x = margin + 2 * mm
                for i, v in enumerate(vals):
                    pdf.drawString(x, y, v)
                    x += col_w[i]
                y -= 7 * mm

        pdf.setFont("Helvetica-Oblique", 8)
        pdf.setFillColorRGB(*preset["footer_rgb"])
        pdf.drawCentredString(
            width / 2,
            15 * mm,
            f"Document généré le {issue_date_str} – {ASSO_NAME} – style {preset_name}",
        )
        pdf.setFillColorRGB(0, 0, 0)

    family_last_name = ""
    if payment.family:
        family_last_name = (
            payment.family.father_last_name
            or payment.family.mother_last_name
            or (payment.family.students[0].last_name if payment.family.students else "")
        )

    school_year_token = payment.family.school_year if payment.family and payment.family.school_year else "annee_scolaire"
    download_date_token = date.today().strftime("%Y-%m-%d")
    filename = (
        f"{filename_token(family_last_name, fallback='famille').upper()}_"
        f"{filename_token(school_year_token)}_"
        f"{filename_token(download_date_token)}.pdf"
    )
    return render_pdf(filename, draw)

