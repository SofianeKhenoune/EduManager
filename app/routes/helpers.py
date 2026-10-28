import io
import os
import re
import unicodedata
from datetime import date, datetime

from flask import abort, current_app, request, send_file
from flask_login import current_user
from werkzeug.security import generate_password_hash

from app import db
from app.authz import OFFICE_ROLES
from app.models import Family, Payment, Role, User

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
except ImportError:
    A4 = None
    canvas = None
    mm = None

WEEKDAY_ORDER = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
PER_PAGE = 12
TIME_SLOTS = {
    "matin": {"start": 9, "end": 12, "start_min": 0, "end_min": 15},
    "après-midi": {"start": 13, "end": 17, "start_min": 45, "end_min": 0},
}

ASSO_NAME = "Association des Musulmans d'Aubervilliers"
ASSO_ADDR = "112 Bd Félix Faure, 93300 Aubervilliers"
ASSO_TEL = "09 86 73 82 18"
ASSO_EMAIL = "contact.ama93@gmail.com"

PDF_PRESETS = {
    "classic": {
        "margin_mm": 20,
        "header_top_mm": 15,
        "logo_mm": 28,
        "brand_rgb": (0.06, 0.47, 0.23),
        "muted_rgb": (0.35, 0.35, 0.35),
        "footer_rgb": (0.5, 0.5, 0.5),
        "signature_w_mm": 55,
        "signature_h_mm": 20,
        "title_size": 16,
        "body_size": 10,
    },
    "modern": {
        "margin_mm": 24,
        "header_top_mm": 14,
        "logo_mm": 36,
        "brand_rgb": (0.00, 0.43, 0.36),
        "muted_rgb": (0.34, 0.40, 0.43),
        "footer_rgb": (0.45, 0.50, 0.52),
        "signature_w_mm": 58,
        "signature_h_mm": 22,
        "title_size": 18,
        "body_size": 10,
    },
    "official": {
        "margin_mm": 18,
        "header_top_mm": 12,
        "logo_mm": 24,
        "brand_rgb": (0.04, 0.30, 0.17),
        "muted_rgb": (0.30, 0.30, 0.30),
        "footer_rgb": (0.42, 0.42, 0.42),
        "signature_w_mm": 70,
        "signature_h_mm": 26,
        "title_size": 15,
        "body_size": 9,
    },
}

PDF_PRESET_ALIASES = {
    "institutionnel-classique": "classic",
    "moderne-aere": "modern",
    "officiel-administratif": "official",
}

_LOGO_PATH_CACHE = None


def optional_int(value: str):
    if value in (None, ""):
        return None
    return int(value)


def optional_float(value: str):
    if value in (None, ""):
        return None
    return float(value)


def parse_date(value: str):
    raw = (value or "").strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise ValueError("Format de date invalide")


def age_on_cutoff(birth: date, cutoff: date) -> int:
    return (cutoff.year - birth.year) - (1 if (birth.month, birth.day) > (cutoff.month, cutoff.day) else 0)


def ensure_family_payment_target(family: Family):
    target_amount = float(family.suggested_amount())
    latest_payment = (
        Payment.query.filter_by(family_id=family.id)
        .order_by(Payment.id.desc())
        .first()
    )

    if latest_payment is None:
        payment = Payment(
            family_id=family.id,
            total_amount=target_amount,
            payment_date=date.today(),
            method=None,
        )
        db.session.add(payment)
        db.session.flush()
        return payment, "created"

    safe_total = max(target_amount, latest_payment.installments_total)
    changed = float(latest_payment.total_amount or 0) != float(safe_total)
    latest_payment.total_amount = safe_total
    return latest_payment, ("updated" if changed else "unchanged")


def family_remaining_amount(family: Family) -> float:
    total_due = 0.0
    total_paid = 0.0
    for payment in family.payments:
        total_due += float(payment.total_amount or 0)
        total_paid += float(payment.installments_total or 0)
    return round(max(total_due - total_paid, 0.0), 2)


def next_due_date(base: date, month_offset: int) -> date:
    year = base.year
    month = base.month
    steps = max(month_offset, 0)
    for _ in range(steps):
        month += 1
        if month > 12:
            month = 1
            year += 1
        if month == 8:
            month = 9
    return date(year, month, 10)


def page():
    return max(request.args.get("page", 1, type=int), 1)


def paginate(query, per_page: int = PER_PAGE):
    return query.paginate(page=page(), per_page=per_page, error_out=False)


def default_school_year(today: date | None = None) -> str:
    current_date = today or date.today()
    if current_date.month >= 6:
        return f"{current_date.year}-{current_date.year + 1}"
    return f"{current_date.year - 1}-{current_date.year}"


def ensure_role_id(role_name: str) -> int:
    role = Role.query.filter_by(name=role_name).first()
    if role is None:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.flush()
    return role.id


def create_user(first_name: str, last_name: str, email: str, password: str, role_name: str):
    existing = User.query.filter_by(email=email).first()
    if existing is not None:
        return None, "Un utilisateur avec cette adresse e-mail existe déjà."

    role_id = ensure_role_id(role_name)
    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=generate_password_hash(password),
        role_id=role_id,
    )
    db.session.add(user)
    db.session.flush()
    return user, None


def default_home_endpoint_for(user: User) -> str:
    if user.has_role(*OFFICE_ROLES):
        return "dashboard.index"
    if user.has_role("parent"):
        return "families.families_page"
    if user.has_role("teacher"):
        return "teachers_portal.teacher_my_classes"
    if user.has_role("volunteer"):
        return "courses.planning_page"
    if user.has_role("student"):
        return "student_portal.student_home"
    return "auth.login"


def render_pdf(filename: str, draw_callback):
    if canvas is None or A4 is None:
        abort(503, description="Le support PDF n'est pas installe.")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    draw_callback(pdf, width, height)
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


def filename_token(value: str, fallback: str = "non_renseigne") -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return fallback
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    underscored = ascii_only.replace(" ", "_")
    clean = re.sub(r"[^a-z0-9_-]", "", underscored)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or fallback


def get_logo_path():
    global _LOGO_PATH_CACHE
    if _LOGO_PATH_CACHE is None:
        candidate = os.path.join(current_app.root_path, "static", "logo.png")
        _LOGO_PATH_CACHE = candidate if os.path.exists(candidate) else ""
    return _LOGO_PATH_CACHE or None


def get_pdf_preset() -> tuple[str, dict]:
    raw = (request.args.get("style") or "classic").strip().lower()
    preset_name = PDF_PRESET_ALIASES.get(raw, raw)
    if preset_name not in PDF_PRESETS:
        preset_name = "classic"
    return preset_name, PDF_PRESETS[preset_name]


def pdf_draw_header(pdf, width, height, preset: dict):
    """Draw logo + association info header. Returns y position below separator."""
    margin = preset["margin_mm"] * mm
    top = height - preset["header_top_mm"] * mm
    logo_size = preset["logo_mm"] * mm
    logo_path = get_logo_path()

    if logo_path:
        pdf.drawImage(
            logo_path,
            margin,
            top - logo_size,
            width=logo_size,
            height=logo_size,
            preserveAspectRatio=True,
            mask="auto",
        )

    text_x = margin + logo_size + 8 * mm
    pdf.setFont("Helvetica-Bold", 13)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(text_x, top - 8 * mm, ASSO_NAME)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(*preset["muted_rgb"])
    pdf.drawString(text_x, top - 15 * mm, ASSO_ADDR)
    pdf.drawString(text_x, top - 21 * mm, f"Tél : {ASSO_TEL}  |  {ASSO_EMAIL}")
    pdf.setFillColorRGB(0, 0, 0)

    y_line = top - logo_size - 4 * mm
    pdf.setStrokeColorRGB(*preset["brand_rgb"])
    pdf.setLineWidth(1.5)
    pdf.line(margin, y_line, width - margin, y_line)
    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setLineWidth(1)
    return y_line - 8 * mm


def teacher_can_mutate_course(course) -> bool:
    """OFFICE can mutate any course; teachers only their own; volunteers cannot."""
    if current_user.has_role(*OFFICE_ROLES):
        return True
    if current_user.has_role("teacher") and current_user.teacher:
        return course.teacher_id == current_user.teacher.id
    return False
