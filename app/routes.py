import csv
import io
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from functools import wraps

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import (
    AttendanceRecord,
    Course,
    CourseSession,
    Department,
    Employee,
    EmployeeLeaveRequest,
    Enrollment,
    Family,
    Payment,
    PaymentInstallment,
    PerformanceReview,
    Position,
    Role,
    SalaryDetail,
    Site,
    Student,
    StudentAssessment,
    Teacher,
    User,
    TARIF_GRID,
    calc_tarif,
)
from app.seed import seed_initial_data

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import mm
except ImportError:
    A4 = None
    canvas = None
    colors = None
    mm = None


main_bp = Blueprint("main", __name__)

ADMIN_ROLES = ("admin", "staff", "manager")
PEDAGOGY_ROLES = ("admin", "staff", "manager", "teacher")
PARENT_ROLES = ("parent",)
WEEKDAY_ORDER = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
PER_PAGE = 12


def roles_required(*role_names: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if not current_user.has_role(*role_names):
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def _optional_int(value: str):
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: str):
    if value in (None, ""):
        return None
    return float(value)


def _parse_date(value: str):
    raw = (value or "").strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise ValueError("Format de date invalide")


def _age_on_cutoff(birth: date, cutoff: date) -> int:
    return (cutoff.year - birth.year) - (1 if (birth.month, birth.day) > (cutoff.month, cutoff.day) else 0)


def _ensure_family_payment_target(family: Family):
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


def _next_due_date(base: date, month_offset: int) -> date:
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


def _page():
    return max(request.args.get("page", 1, type=int), 1)


def _paginate(query, per_page: int = PER_PAGE):
    return query.paginate(page=_page(), per_page=per_page, error_out=False)


def _default_school_year(today: date | None = None) -> str:
    current_date = today or date.today()
    if current_date.month >= 6:
        return f"{current_date.year}-{current_date.year + 1}"
    return f"{current_date.year - 1}-{current_date.year}"


def _ensure_role_id(role_name: str) -> int:
    role = Role.query.filter_by(name=role_name).first()
    if role is None:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.flush()
    return role.id


def _create_user(first_name: str, last_name: str, email: str, password: str, role_name: str):
    existing = User.query.filter_by(email=email).first()
    if existing is not None:
        return None, "Un utilisateur avec cette adresse e-mail existe déjà."

    role_id = _ensure_role_id(role_name)
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


def _family_access_allowed(family: Family):
    if current_user.has_role(*ADMIN_ROLES):
        return True
    return current_user.has_role(*PARENT_ROLES) and family.user_id == current_user.id


def _student_access_allowed(student: Student):
    if current_user.has_role(*ADMIN_ROLES, "teacher"):
        return True
    return current_user.has_role(*PARENT_ROLES) and student.family and student.family.user_id == current_user.id


def _render_pdf(filename: str, draw_callback):
    if canvas is None or A4 is None:
        abort(503, description="Le support PDF n'est pas installe.")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    draw_callback(pdf, width, height)
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


def _filename_token(value: str, fallback: str = "non_renseigne") -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return fallback
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    underscored = ascii_only.replace(" ", "_")
    clean = re.sub(r"[^a-z0-9_-]", "", underscored)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or fallback
_ASSO_NAME  = "Association des Musulmans d'Aubervilliers"
_ASSO_ADDR  = "112 Bd Félix Faure, 93300 Aubervilliers"
_ASSO_TEL   = "09 86 73 82 18"
_ASSO_EMAIL = "contact.ama93@gmail.com"

# PDF visual presets
_PDF_PRESETS = {
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

_PDF_PRESET_ALIASES = {
    "institutionnel-classique": "classic",
    "moderne-aere": "modern",
    "officiel-administratif": "official",
}

_LOGO_PATH_CACHE = None


def _get_logo_path():
    global _LOGO_PATH_CACHE
    if _LOGO_PATH_CACHE is None:
        import os
        candidate = os.path.join(current_app.root_path, "static", "logo.png")
        _LOGO_PATH_CACHE = candidate if os.path.exists(candidate) else ""
    return _LOGO_PATH_CACHE or None


def _get_pdf_preset() -> tuple[str, dict]:
    raw = (request.args.get("style") or "classic").strip().lower()
    preset_name = _PDF_PRESET_ALIASES.get(raw, raw)
    if preset_name not in _PDF_PRESETS:
        preset_name = "classic"
    return preset_name, _PDF_PRESETS[preset_name]


def _pdf_draw_header(pdf, width, height, preset: dict):
    """Draw logo + association info header. Returns y position below separator."""
    margin = preset["margin_mm"] * mm
    top = height - preset["header_top_mm"] * mm
    logo_size = preset["logo_mm"] * mm
    logo_path = _get_logo_path()

    if logo_path:
        pdf.drawImage(logo_path, margin, top - logo_size, width=logo_size, height=logo_size,
                      preserveAspectRatio=True, mask="auto")

    text_x = margin + logo_size + 8 * mm
    pdf.setFont("Helvetica-Bold", 13)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(text_x, top - 8 * mm, _ASSO_NAME)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(*preset["muted_rgb"])
    pdf.drawString(text_x, top - 15 * mm, _ASSO_ADDR)
    pdf.drawString(text_x, top - 21 * mm, f"Tél : {_ASSO_TEL}  |  {_ASSO_EMAIL}")
    pdf.setFillColorRGB(0, 0, 0)

    y_line = top - logo_size - 4 * mm
    pdf.setStrokeColorRGB(*preset["brand_rgb"])
    pdf.setLineWidth(1.5)
    pdf.line(margin, y_line, width - margin, y_line)
    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setLineWidth(1)
    return y_line - 8 * mm


@main_bp.app_errorhandler(403)
def forbidden(_error):
    return render_template("forbidden.html"), 403


@main_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return render_template("index.html")
    
    # Basic KPIs
    kpis = {
        "students": Student.query.count(),
        "teachers": Teacher.query.count(),
        "courses": Course.query.count(),
        "employees": Employee.query.count(),
        "active_enrollments": Enrollment.query.filter_by(status="active").count(),
        "families": Family.query.count(),
        "sites": Site.query.count(),
        "sessions": CourseSession.query.count(),
    }
    
    # Payment analytics
    payments_total = db.session.query(func.coalesce(func.sum(Payment.total_amount), 0)).filter(
        Payment.family_id != None
    ).scalar() or 0
    payments_collected = db.session.query(func.coalesce(func.sum(PaymentInstallment.amount), 0)).join(
        Payment, Payment.id == PaymentInstallment.payment_id
    ).filter(
        PaymentInstallment.method != None,
        Payment.family_id != None,
    ).scalar() or 0
    payment_collection_percent = round(
        (float(payments_collected) / float(payments_total) * 100) if payments_total > 0 else 0, 1
    )
    
    # Course occupancy
    active_courses = Course.query.all()
    average_occupancy = round(
        sum(course.occupancy_rate for course in active_courses) / len(active_courses), 1
    ) if active_courses else 0
    
    # Upcoming sessions
    upcoming_sessions = (
        CourseSession.query.filter(CourseSession.session_date >= date.today())
        .order_by(CourseSession.session_date.asc())
        .limit(8)
        .all()
    )
    
    # Top courses by enrollment
    top_courses = sorted(active_courses, key=lambda course: course.active_enrollments_count, reverse=True)[:6]
    
    # Pending items
    pending_leaves = EmployeeLeaveRequest.query.filter_by(status="pending").count()
    
    # Recent payments with pending/collected status
    all_payments = Payment.query.filter(Payment.family_id != None).order_by(Payment.payment_date.desc()).limit(12).all()
    pending_payments = [p for p in all_payments if p.remaining_amount > 0][:5]
    recent_collected = PaymentInstallment.query.join(
        Payment, Payment.id == PaymentInstallment.payment_id
    ).filter(
        PaymentInstallment.method != None,
        Payment.family_id != None,
    ).order_by(PaymentInstallment.payment_date.desc()).limit(8).all()
    
    # Late payments (> 30 days overdue)
    from datetime import timedelta
    late_threshold = date.today() - timedelta(days=30)
    late_count = Payment.query.filter(
        Payment.family_id != None,
        Payment.payment_date != None,
        Payment.payment_date < late_threshold
    ).count()
    
    return render_template(
        "index.html",
        kpis=kpis,
        payments_total=float(payments_total),
        payments_collected=float(payments_collected),
        payment_collection_percent=payment_collection_percent,
        average_occupancy=average_occupancy,
        upcoming_sessions=upcoming_sessions,
        top_courses=top_courses,
        pending_leaves=pending_leaves,
        pending_payments=pending_payments,
        recent_collected=recent_collected,
        late_count=late_count,
    )


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session.permanent = True
            login_user(user, remember=request.form.get("remember") == "1")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.index"))
        flash("Email ou mot de passe incorrect.", "danger")
    return render_template("login.html")


@main_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("main.login"))


@main_bp.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@main_bp.route("/api/dashboard")
@login_required
def api_dashboard():
    """Comprehensive dashboard API with role-based filtering"""
    from datetime import timedelta
    from sqlalchemy import extract
    
    # Payment analytics
    payments_total = db.session.query(func.coalesce(func.sum(Payment.total_amount), 0)).filter(
        Payment.family_id != None
    ).scalar() or 0
    payments_collected = db.session.query(func.coalesce(func.sum(PaymentInstallment.amount), 0)).join(
        Payment, Payment.id == PaymentInstallment.payment_id
    ).filter(
        PaymentInstallment.method != None,
        Payment.family_id != None,
    ).scalar() or 0
    
    # Course occupancy
    active_courses = Course.query.all()
    avg_occupancy = round(
        sum(course.occupancy_rate for course in active_courses) / len(active_courses), 1
    ) if active_courses else 0
    
    # Chart data: enrollments by level
    courses_by_level = db.session.query(
        Course.level, func.count(Enrollment.id)
    ).outerjoin(Enrollment, (Course.id == Enrollment.course_id) & (Enrollment.status == "active")).group_by(
        Course.level
    ).all()
    
    # Chart data: payments collection (last 12 months)
    payments_by_month = db.session.query(
        extract('month', PaymentInstallment.payment_date).cast(db.Integer),
        func.count(PaymentInstallment.id)
    ).join(
        Payment, Payment.id == PaymentInstallment.payment_id
    ).filter(
        PaymentInstallment.method != None,
        Payment.family_id != None,
    ).group_by(
        extract('month', PaymentInstallment.payment_date)
    ).order_by(extract('month', PaymentInstallment.payment_date)).all()
    
    # Pending and late payments count
    all_payments = Payment.query.filter(Payment.family_id != None).all()
    pending_payments_count = len([p for p in all_payments if p.remaining_amount > 0])
    
    late_threshold = date.today() - timedelta(days=30)
    late_payments = len([
        p for p in all_payments 
        if p.payment_date and p.payment_date < late_threshold and p.remaining_amount > 0
    ])
    
    # Recent activity
    recent_collected = PaymentInstallment.query.join(
        Payment, Payment.id == PaymentInstallment.payment_id
    ).filter(
        PaymentInstallment.method != None,
        Payment.family_id != None,
    ).order_by(PaymentInstallment.payment_date.desc()).limit(8).all()
    
    base_data = {
        "students": Student.query.count(),
        "teachers": Teacher.query.count(),
        "courses": Course.query.count(),
        "employees": Employee.query.count(),
        "active_enrollments": Enrollment.query.filter_by(status="active").count(),
        "sites": Site.query.count(),
        "families": Family.query.count(),
        "sessions": CourseSession.query.count(),
        "payments_total": float(payments_total),
        "payments_collected": float(payments_collected),
        "payment_collection_percent": round(
            (float(payments_collected) / float(payments_total) * 100) if payments_total > 0 else 0, 1
        ),
        "avg_occupancy": avg_occupancy,
        "pending_leaves": EmployeeLeaveRequest.query.filter_by(status="pending").count(),
        "pending_payments_count": pending_payments_count,
        "late_payments": late_payments,
        "chart_data": {
            "enrollments_by_level": {
                "labels": [level or "Non spécifié" for level, _ in courses_by_level],
                "data": [int(count) for _, count in courses_by_level]
            },
            "payments_by_month": {
                "labels": [f"Mois {int(m)}" for m, _ in payments_by_month],
                "data": [int(count) for _, count in payments_by_month]
            }
        },
        "recent_collected": [
            {
                "id": p.id,
                "created_at": p.payment_date.isoformat() if p.payment_date else date.today().isoformat()
            }
            for p in recent_collected
        ]
    }
    
    # Role-based enrichment
    if current_user.has_role("teacher"):
        teacher = Teacher.query.filter_by(user_id=current_user.id).first()
        if teacher:
            my_courses = Course.query.filter_by(teacher_id=teacher.id).all()
            base_data["my_courses_count"] = len(my_courses)
            base_data["my_active_enrollments"] = sum(
                Enrollment.query.filter_by(course_id=c.id, status="active").count() for c in my_courses
            )
            base_data["my_sessions_today"] = CourseSession.query.filter(
                CourseSession.course_id.in_([c.id for c in my_courses]),
                CourseSession.session_date == date.today()
            ).count()
    
    elif current_user.has_role("parent"):
        family = Family.query.filter_by(user_id=current_user.id).first()
        if family:
            base_data["my_students"] = len(family.students)
            base_data["my_active_enrollments"] = sum(
                Enrollment.query.filter_by(student_id=s.id, status="active").count() 
                for s in family.students
            )
            latest_payment = Payment.query.filter_by(family_id=family.id).order_by(Payment.id.desc()).first()
            if latest_payment:
                base_data["my_payment_remaining"] = float(latest_payment.remaining_amount)
    
    return jsonify(base_data), 200


@main_bp.route("/api/kpis")
@login_required
def api_kpis():
    """Compatibility endpoint for legacy frontend scripts."""
    payments_total = db.session.query(func.coalesce(func.sum(Payment.total_amount), 0)).filter(
        Payment.family_id != None
    ).scalar() or 0
    payments_collected = db.session.query(func.coalesce(func.sum(PaymentInstallment.amount), 0)).join(
        Payment, Payment.id == PaymentInstallment.payment_id
    ).filter(
        PaymentInstallment.method != None,
        Payment.family_id != None,
    ).scalar() or 0
    data = {
        "students": Student.query.count(),
        "teachers": Teacher.query.count(),
        "courses": Course.query.count(),
        "employees": Employee.query.count(),
        "active_enrollments": Enrollment.query.filter_by(status="active").count(),
        "sites": Site.query.count(),
        "families": Family.query.count(),
        "sessions": CourseSession.query.count(),
        "payments_total": float(payments_total),
        "payments_collected": float(payments_collected),
    }
    return jsonify(data), 200


@main_bp.route("/students", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def students_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            birth_date = request.form.get("birth_date", "").strip()
            site_id = _optional_int(request.form.get("site_id"))
            gender = request.form.get("gender", "").strip() or None
            is_reinscription = request.form.get("is_reinscription") == "1"
            lives_alone = request.form.get("lives_alone") == "1"
            default_school_year = _default_school_year()

            if not all([first_name, last_name, birth_date, gender]) or site_id is None:
                flash("Prénom, nom, date de naissance, genre et site sont obligatoires.", "warning")
                return redirect(url_for("main.students_page"))

            parsed_birth = _parse_date(birth_date)
            cutoff = date(date.today().year, 10, 1)
            age_on_cutoff = _age_on_cutoff(parsed_birth, cutoff)
            force_underage = request.form.get("force_underage") == "1"
            if age_on_cutoff < 6 and not force_underage:
                flash("L'élève doit avoir au moins 6 ans au 1er octobre de l'année en cours.", "warning")
                return redirect(url_for("main.students_page"))
            if age_on_cutoff < 6 and force_underage:
                flash("Inscription en dessous de l'âge recommandée (validation forcée).", "warning")

            family_id = _optional_int(request.form.get("family_id"))
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
                address_number = _optional_int(request.form.get("address_number"))
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
                    return redirect(url_for("main.students_page"))

                if not (father_email or mother_email):
                    flash("Au moins un e-mail parent est obligatoire.", "warning")
                    return redirect(url_for("main.students_page"))

                if not (father_phone or mother_phone):
                    flash("Au moins un numéro de téléphone parent est obligatoire.", "warning")
                    return redirect(url_for("main.students_page"))

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
            return redirect(url_for("main.enrollments_page", student_id=student.id, quick_flow=1))
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'élève. Vérifiez les données saisies.", "danger")
        return redirect(url_for("main.students_page"))

    query = request.args.get("q", "").strip()
    students_query = Student.query
    if query:
        like_query = f"%{query}%"
        students_query = students_query.filter(
            or_(
                Student.first_name.ilike(like_query),
                Student.last_name.ilike(like_query),
            )
        )
    students_pagination = _paginate(students_query.order_by(Student.last_name.asc(), Student.first_name.asc()))
    sites = Site.query.order_by(Site.name.asc()).all()
    families = Family.query.order_by(Family.father_last_name.asc()).all()
    default_school_year = _default_school_year()
    return render_template(
        "students.html",
        students=students_pagination.items,
        students_pagination=students_pagination,
        sites=sites,
        families=families,
        default_school_year=default_school_year,
        search_query=query,
    )


@main_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == "POST":
        try:
            student.first_name = request.form.get("first_name", "").strip()
            student.last_name = request.form.get("last_name", "").strip()
            birth_date = request.form.get("birth_date", "").strip()
            if birth_date:
                student.birth_date = _parse_date(birth_date)
            student.site_id = _optional_int(request.form.get("site_id"))
            student.family_id = _optional_int(request.form.get("family_id"))
            student.gender = request.form.get("gender", "").strip() or None
            student.is_reinscription = request.form.get("is_reinscription") == "1"
            student.lives_alone = request.form.get("lives_alone") == "1"
            db.session.commit()
            flash("Élève mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
        return redirect(url_for("main.edit_student", student_id=student_id))

    sites = Site.query.order_by(Site.name.asc()).all()
    families = Family.query.order_by(Family.id.asc()).all()
    return render_template("edit_student.html", student=student, sites=sites, families=families)


@main_bp.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
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
        return redirect(url_for("main.family_detail", family_id=family_id, suggest_delete=1))

    return redirect(url_for("main.students_page"))


@main_bp.route("/teachers", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def teachers_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            subject = request.form.get("subject", "").strip()

            if not all([first_name, last_name, email, password]):
                flash("Les champs prenom, nom, adresse e-mail et mot de passe sont obligatoires.", "warning")
                return redirect(url_for("main.teachers_page"))

            user, error = _create_user(first_name, last_name, email, password, "teacher")
            if error:
                db.session.rollback()
                flash(error, "warning")
                return redirect(url_for("main.teachers_page"))

            teacher = Teacher(user_id=user.id, subject=subject or None)
            db.session.add(teacher)
            db.session.commit()
            flash("Enseignant ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'enseignant.", "danger")

        return redirect(url_for("main.teachers_page"))

    teachers_pagination = _paginate(Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()))
    return render_template("teachers.html", teachers=teachers_pagination.items, teachers_pagination=teachers_pagination)


@main_bp.route("/teachers/<int:teacher_id>/edit", methods=["GET", "POST"])
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
                    return redirect(url_for("main.edit_teacher", teacher_id=teacher_id))
                teacher.user.email = email
            teacher.subject = request.form.get("subject", "").strip() or None
            db.session.commit()
            flash("Enseignant mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour.", "danger")
        return redirect(url_for("main.edit_teacher", teacher_id=teacher_id))

    return render_template("edit_teacher.html", teacher=teacher)


@main_bp.route("/teachers/<int:teacher_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    if teacher.courses:
        flash("Impossible de supprimer cet enseignant : il est affecté a des cours.", "warning")
        return redirect(url_for("main.teachers_page"))
    user = teacher.user
    db.session.delete(teacher)
    db.session.delete(user)
    db.session.commit()
    flash("Enseignant supprime.", "success")
    return redirect(url_for("main.teachers_page"))


@main_bp.route("/employees", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def employees_page():
    if request.method == "POST":
        try:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            hire_date = request.form.get("hire_date", "").strip()
            employee_code = request.form.get("employee_code", "").strip()
            position_id = _optional_int(request.form.get("position_id"))
            department_id = _optional_int(request.form.get("department_id"))

            if not all([first_name, last_name, email, password, hire_date, employee_code]):
                flash("Des champs obligatoires de l'employé sont manquants.", "warning")
                return redirect(url_for("main.employees_page"))

            if not employee_code.isdigit():
                flash("Le matricule doit être un nombre entier.", "warning")
                return redirect(url_for("main.employees_page"))

            employee_code = employee_code.zfill(5)
            existing_employee = Employee.query.filter_by(employee_id=employee_code).first()
            if existing_employee:
                flash(f"Le matricule {employee_code} est déjà utilisé.", "warning")
                return redirect(url_for("main.employees_page"))

            user, error = _create_user(first_name, last_name, email, password, "staff")
            if error:
                db.session.rollback()
                flash(error, "warning")
                return redirect(url_for("main.employees_page"))

            employee = Employee(
                user_id=user.id,
                hire_date=_parse_date(hire_date),
                employee_id=employee_code,
                position_id=position_id,
                department_id=department_id,
            )
            db.session.add(employee)
            db.session.commit()
            flash("Employe ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter l'employé. Vérifiez le matricule et la date d'embauche.", "danger")

        return redirect(url_for("main.employees_page"))

    employees_pagination = _paginate(Employee.query.join(User, Employee.user_id == User.id).order_by(User.last_name.asc()))
    positions = Position.query.order_by(Position.title.asc()).all()
    departments = Department.query.order_by(Department.name.asc()).all()
    return render_template(
        "employees.html",
        employees=employees_pagination.items,
        employees_pagination=employees_pagination,
        positions=positions,
        departments=departments,
    )


@main_bp.route("/employees/<int:emp_id>", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def employee_detail(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if action == "salary":
                detail = SalaryDetail(
                    employee_id=employee.id,
                    contract_type=request.form.get("contract_type", "").strip() or (employee.contract_type or "CDI"),
                    hourly_rate=_optional_float(request.form.get("hourly_rate")),
                    annual_salary=_optional_float(request.form.get("annual_salary")),
                    benefits=request.form.get("benefits", "").strip() or None,
                    effective_date=_parse_date(request.form.get("effective_date")) if request.form.get("effective_date") else date.today(),
                    notes=request.form.get("notes", "").strip() or None,
                )
                db.session.add(detail)
                flash("Historique salarial ajoute.", "success")
            elif action == "review":
                review = PerformanceReview(
                    employee_id=employee.id,
                    review_date=_parse_date(request.form.get("review_date")),
                    rating=_optional_int(request.form.get("rating")) or 1,
                    comments=request.form.get("comments", "").strip() or None,
                    goals=request.form.get("goals", "").strip() or None,
                )
                db.session.add(review)
                flash("Évaluation employee ajoutée.", "success")
            elif action == "leave":
                leave_request = EmployeeLeaveRequest(
                    employee_id=employee.id,
                    start_date=_parse_date(request.form.get("start_date")),
                    end_date=_parse_date(request.form.get("end_date")),
                    leave_type=request.form.get("leave_type", "").strip() or "Congé paye",
                    status=request.form.get("status", "pending").strip() or "pending",
                    comments=request.form.get("comments", "").strip() or None,
                )
                db.session.add(leave_request)
                flash("Demande de congé ajoutée.", "success")
            db.session.commit()
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'enregistrer cette mise à jour RH.", "danger")
        return redirect(url_for("main.employee_detail", emp_id=emp_id))
    return render_template("employee_detail.html", employee=employee)


@main_bp.route("/employees/<int:emp_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_employee(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        try:
            employee.user.first_name = request.form.get("first_name", "").strip()
            employee.user.last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            if email != employee.user.email:
                existing = User.query.filter_by(email=email).first()
                if existing:
                    flash("Cette adresse e-mail est déjà utilisee.", "warning")
                    return redirect(url_for("main.edit_employee", emp_id=emp_id))
                employee.user.email = email
            employee.user.phone_number = request.form.get("phone_number", "").strip() or None
            hire_date = request.form.get("hire_date", "").strip()
            if hire_date:
                employee.hire_date = _parse_date(hire_date)
            employee.position_id = _optional_int(request.form.get("position_id"))
            employee.department_id = _optional_int(request.form.get("department_id"))
            employee.civility = request.form.get("civility", "").strip() or None
            employee.birth_name = request.form.get("birth_name", "").strip() or None
            birth_date = request.form.get("birth_date", "").strip()
            employee.birth_date = _parse_date(birth_date) if birth_date else None
            employee.birth_place = request.form.get("birth_place", "").strip() or None
            employee.nationality = request.form.get("nationality", "").strip() or None
            employee.address = request.form.get("address", "").strip() or None
            employee.zip_code = request.form.get("zip_code", "").strip() or None
            employee.city = request.form.get("city", "").strip() or None
            employee.contract_type = request.form.get("contract_type", "").strip() or None
            trial_period_end = request.form.get("trial_period_end", "").strip()
            employee.trial_period_end = _parse_date(trial_period_end) if trial_period_end else None
            contract_end_date = request.form.get("contract_end_date", "").strip()
            employee.contract_end_date = _parse_date(contract_end_date) if contract_end_date else None
            employee.level = request.form.get("level", "").strip() or None
            employee.index_grade = request.form.get("index_grade", "").strip() or None
            employee.hours_per_week = _optional_float(request.form.get("hours_per_week", "").strip())
            employee.hours_per_month = _optional_float(request.form.get("hours_per_month", "").strip())
            employee.hourly_rate = _optional_float(request.form.get("hourly_rate", "").strip())
            employee.monthly_salary = _optional_float(request.form.get("monthly_salary", "").strip())
            employee.navigo_pass = request.form.get("navigo_pass") == "1"
            employee.pas_rate = _optional_float(request.form.get("pas_rate", "").strip())
            db.session.commit()
            flash("Employe mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour. Vérifiez les données.", "danger")
        return redirect(url_for("main.edit_employee", emp_id=emp_id))

    positions = Position.query.order_by(Position.title.asc()).all()
    departments = Department.query.order_by(Department.name.asc()).all()
    return render_template("edit_employee.html", employee=employee, positions=positions, departments=departments)


@main_bp.route("/employees/<int:emp_id>/leave/<int:leave_id>/status", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def update_leave_status(emp_id, leave_id):
    employee = Employee.query.get_or_404(emp_id)
    leave_request = EmployeeLeaveRequest.query.get_or_404(leave_id)
    if leave_request.employee_id != employee.id:
        abort(404)
    status = request.form.get("status", "pending").strip()
    if status not in ("pending", "approved", "rejected"):
        flash("Statut de congé invalide.", "warning")
    else:
        leave_request.status = status
        db.session.commit()
        flash("Statut du congé mis à jour.", "success")
    return redirect(url_for("main.employee_detail", emp_id=emp_id))


@main_bp.route("/employees/<int:emp_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_employee(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    user = employee.user
    db.session.delete(employee)
    db.session.delete(user)
    db.session.commit()
    flash("Employe supprime.", "success")
    return redirect(url_for("main.employees_page"))


@main_bp.route("/sites", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def sites_page():
    if request.method == "POST":
        site = Site(
            name=request.form.get("name", "").strip(),
            address=request.form.get("address", "").strip() or None,
        )
        db.session.add(site)
        try:
            db.session.commit()
            flash("Site ajoute.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Impossible d'ajouter ce site.", "danger")
        return redirect(url_for("main.sites_page"))
    sites_pagination = _paginate(Site.query.order_by(Site.name.asc()))
    return render_template("sites.html", sites=sites_pagination.items, sites_pagination=sites_pagination)


@main_bp.route("/sites/<int:site_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_site(site_id):
    site = Site.query.get_or_404(site_id)
    site.name = request.form.get("name", "").strip()
    site.address = request.form.get("address", "").strip() or None
    try:
        db.session.commit()
        flash("Site mis à jour.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Impossible de mettre a jour ce site.", "danger")
    return redirect(url_for("main.sites_page"))


@main_bp.route("/sites/<int:site_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_site(site_id):
    site = Site.query.get_or_404(site_id)
    if site.courses or site.students:
        flash("Impossible de supprimer ce site : il est encore utilisé.", "warning")
    else:
        db.session.delete(site)
        db.session.commit()
        flash("Site supprime.", "success")
    return redirect(url_for("main.sites_page"))


@main_bp.route("/departments", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def departments_page():
    if request.method == "POST":
        department = Department(
            name=request.form.get("name", "").strip(),
            manager_id=_optional_int(request.form.get("manager_id")),
        )
        db.session.add(department)
        try:
            db.session.commit()
            flash("Departement ajoute.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Impossible d'ajouter ce département.", "danger")
        return redirect(url_for("main.departments_page"))
    departments_pagination = _paginate(Department.query.order_by(Department.name.asc()))
    managers = Employee.query.join(User, Employee.user_id == User.id).order_by(User.last_name.asc()).all()
    return render_template(
        "departments.html",
        departments=departments_pagination.items,
        departments_pagination=departments_pagination,
        managers=managers,
    )


@main_bp.route("/departments/<int:department_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_department(department_id):
    department = Department.query.get_or_404(department_id)
    department.name = request.form.get("name", "").strip()
    department.manager_id = _optional_int(request.form.get("manager_id"))
    try:
        db.session.commit()
        flash("Departement mis à jour.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Impossible de mettre a jour ce département.", "danger")
    return redirect(url_for("main.departments_page"))


@main_bp.route("/departments/<int:department_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_department(department_id):
    department = Department.query.get_or_404(department_id)
    if department.employees:
        flash("Impossible de supprimer ce département : des employés y sont rattaches.", "warning")
    else:
        db.session.delete(department)
        db.session.commit()
        flash("Departement supprime.", "success")
    return redirect(url_for("main.departments_page"))


@main_bp.route("/positions", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def positions_page():
    if request.method == "POST":
        position = Position(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip() or None,
        )
        db.session.add(position)
        try:
            db.session.commit()
            flash("Poste ajoute.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Impossible d'ajouter ce poste.", "danger")
        return redirect(url_for("main.positions_page"))
    positions_pagination = _paginate(Position.query.order_by(Position.title.asc()))
    return render_template("positions.html", positions=positions_pagination.items, positions_pagination=positions_pagination)


@main_bp.route("/positions/<int:position_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_position(position_id):
    position = Position.query.get_or_404(position_id)
    position.title = request.form.get("title", "").strip()
    position.description = request.form.get("description", "").strip() or None
    try:
        db.session.commit()
        flash("Poste mis à jour.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Impossible de mettre a jour ce poste.", "danger")
    return redirect(url_for("main.positions_page"))


@main_bp.route("/positions/<int:position_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_position(position_id):
    position = Position.query.get_or_404(position_id)
    if position.employees:
        flash("Impossible de supprimer ce poste : des employés y sont rattaches.", "warning")
    else:
        db.session.delete(position)
        db.session.commit()
        flash("Poste supprime.", "success")
    return redirect(url_for("main.positions_page"))


@main_bp.route("/courses", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def courses_page():
    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            teacher_id = _optional_int(request.form.get("teacher_id"))
            site_id = _optional_int(request.form.get("site_id"))
            level = request.form.get("level", "").strip() or None
            day = request.form.get("day", "").strip() or None
            time_slot = request.form.get("time_slot", "").strip() or None
            start_hour = _optional_int(request.form.get("start_hour"))
            end_hour = _optional_int(request.form.get("end_hour"))

            if not title or teacher_id is None:
                flash("Le titre du cours et l'enseignant sont obligatoires.", "warning")
                return redirect(url_for("main.courses_page"))

            course = Course(
                title=title,
                description=request.form.get("description", "").strip() or None,
                teacher_id=teacher_id,
                site_id=site_id,
                level=level,
                day=day,
                time_slot=time_slot,
                start_hour=start_hour,
                end_hour=end_hour,
                room=request.form.get("room", "").strip() or None,
                capacity=_optional_int(request.form.get("capacity")) or 20,
            )
            db.session.add(course)
            db.session.commit()
            flash("Cours ajouté avec succès.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'ajouter le cours. Vérifiez les contraintes horaires.", "danger")

        return redirect(url_for("main.courses_page"))

    courses_query = Course.query
    if current_user.has_role("teacher"):
        teacher = current_user.teacher
        if teacher:
            courses_query = courses_query.filter(Course.teacher_id == teacher.id)
    courses_pagination = _paginate(courses_query.order_by(Course.id.desc()))
    teachers = Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template(
        "courses.html",
        courses=courses_pagination.items,
        courses_pagination=courses_pagination,
        teachers=teachers,
        sites=sites,
    )


@main_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == "POST":
        try:
            course.title = request.form.get("title", "").strip()
            course.description = request.form.get("description", "").strip() or None
            teacher_id = _optional_int(request.form.get("teacher_id"))
            if not teacher_id:
                flash("L'enseignant est obligatoire.", "warning")
                return redirect(url_for("main.edit_course", course_id=course_id))
            course.teacher_id = teacher_id
            course.site_id = _optional_int(request.form.get("site_id"))
            course.level = request.form.get("level", "").strip() or None
            course.day = request.form.get("day", "").strip() or None
            course.time_slot = request.form.get("time_slot", "").strip() or None
            course.start_hour = _optional_int(request.form.get("start_hour"))
            course.end_hour = _optional_int(request.form.get("end_hour"))
            course.room = request.form.get("room", "").strip() or None
            course.capacity = _optional_int(request.form.get("capacity")) or 20
            db.session.commit()
            flash("Cours mis à jour.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Erreur lors de la mise à jour. Vérifiez les contraintes horaires.", "danger")
        return redirect(url_for("main.edit_course", course_id=course_id))

    teachers = Teacher.query.join(User, Teacher.user_id == User.id).order_by(User.last_name.asc()).all()
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template("edit_course.html", course=course, teachers=teachers, sites=sites)


@main_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash("Cours supprime.", "success")
    return redirect(url_for("main.courses_page"))


@main_bp.route("/planning", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def planning_page():
    if request.method == "POST":
        try:
            session = CourseSession(
                course_id=_optional_int(request.form.get("course_id")),
                session_date=_parse_date(request.form.get("session_date")),
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
        return redirect(url_for("main.planning_page"))

    site_filter = _optional_int(request.args.get("site_id"))
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


@main_bp.route("/attendance/sessions/<int:session_id>", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def session_detail(session_id):
    session = CourseSession.query.get_or_404(session_id)
    if current_user.has_role("teacher"):
        teacher = current_user.teacher
        if teacher is None or session.course.teacher_id != teacher.id:
            abort(403)
    if request.method == "POST":
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
        return redirect(url_for("main.session_detail", session_id=session_id))

    existing_records = {record.student_id: record for record in session.attendance_records}
    active_students = [enrollment.student for enrollment in session.course.enrollments if enrollment.status == "active"]
    return render_template(
        "attendance_session.html",
        session=session,
        active_students=active_students,
        existing_records=existing_records,
    )


@main_bp.route("/assessments", methods=["GET", "POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def assessments_page():
    if request.method == "POST":
        try:
            assessment = StudentAssessment(
                student_id=_optional_int(request.form.get("student_id")),
                course_id=_optional_int(request.form.get("course_id")),
                assessment_date=_parse_date(request.form.get("assessment_date")) if request.form.get("assessment_date") else date.today(),
                category=request.form.get("category", "").strip() or "Controle continu",
                score=_optional_float(request.form.get("score")),
                max_score=_optional_float(request.form.get("max_score")) or 20,
                appreciation=request.form.get("appreciation", "").strip() or None,
            )
            db.session.add(assessment)
            db.session.commit()
            flash("Évaluation enregistrée.", "success")
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash("Impossible d'enregistrer cette évaluation.", "danger")
        return redirect(url_for("main.assessments_page"))

    student_filter = _optional_int(request.args.get("student_id"))
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
    assessments_pagination = _paginate(assessments_query.order_by(StudentAssessment.assessment_date.desc()))
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


@main_bp.route("/assessments/<int:assessment_id>/delete", methods=["POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def delete_assessment(assessment_id):
    assessment = StudentAssessment.query.get_or_404(assessment_id)
    db.session.delete(assessment)
    db.session.commit()
    flash("Évaluation supprimée.", "success")
    return redirect(url_for("main.assessments_page"))


@main_bp.route("/enrollments", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def enrollments_page():
    selected_student_id = _optional_int(request.args.get("student_id"))
    quick_flow = request.args.get("quick_flow") == "1"

    if request.method == "POST":
        student_id = _optional_int(request.form.get("student_id"))
        course_id = _optional_int(request.form.get("course_id"))
        status = request.form.get("status", "active").strip()
        quick_flow = request.form.get("quick_flow") == "1"

        if not student_id or not course_id:
            flash("Élève et cours sont obligatoires.", "warning")
            return redirect(url_for("main.enrollments_page", student_id=student_id, quick_flow=1 if quick_flow else None))

        existing = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
        if existing:
            flash("Cet élève est déjà inscrit a ce cours.", "warning")
            return redirect(url_for("main.enrollments_page", student_id=student_id, quick_flow=1 if quick_flow else None))

        enrollment = Enrollment(student_id=student_id, course_id=course_id, status=status)
        db.session.add(enrollment)
        db.session.commit()

        payment_action = None
        family_payment = None
        if status == "active":
            student = Student.query.get(student_id)
            family = student.family if student else None
            if family is not None:
                family_payment, payment_action = _ensure_family_payment_target(family)
                db.session.commit()

        if quick_flow:
            student = Student.query.get(student_id)
            if student and student.family_id:
                if family_payment is not None:
                    flash("Inscription ajoutée. Configurez maintenant le paiement.", "success")
                    return redirect(url_for("main.payment_quick_setup", payment_id=family_payment.id))
                flash("Inscription ajoutée. Passez maintenant au paiement.", "success")
                return redirect(url_for("main.payments_page", family_id=student.family_id, quick_flow=1))

        if payment_action == "created":
            flash("Inscription ajoutée. Paiement créé automatiquement.", "success")
        elif payment_action == "updated":
            flash("Inscription ajoutée. Montant familial recalculé en tenant compte des sommes déjà réglées.", "success")
        else:
            flash("Inscription ajoutée.", "success")
        return redirect(url_for("main.enrollments_page", student_id=student_id if quick_flow else None, quick_flow=1 if quick_flow else None))

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
    enrollments_pagination = _paginate(query.order_by(Student.last_name.asc()))
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


@main_bp.route("/enrollments/<int:enrollment_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_enrollment(enrollment_id):
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    new_status = request.form.get("status", "").strip()
    if new_status in ("active", "annulee", "en_attente"):
        enrollment.status = new_status
        db.session.commit()
        flash("Statut mis à jour.", "success")
    else:
        flash("Statut invalide.", "warning")
    return redirect(url_for("main.enrollments_page"))


@main_bp.route("/enrollments/<int:enrollment_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_enrollment(enrollment_id):
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    db.session.delete(enrollment)
    db.session.commit()
    flash("Inscription supprimée.", "success")
    return redirect(url_for("main.enrollments_page"))


@main_bp.route("/families", methods=["GET", "POST"])
@login_required
def families_page():
    if not current_user.has_role(*ADMIN_ROLES, *PARENT_ROLES):
        abort(403)
    if request.method == "POST":
        if not current_user.has_role(*ADMIN_ROLES):
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
            address_number=_optional_int(request.form.get("address_number")),
            street=request.form.get("street", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            zip_code=request.form.get("zip_code", "").strip() or None,
        )
        db.session.add(family)
        db.session.commit()
        flash("Famille créée.", "success")
        return redirect(url_for("main.family_detail", family_id=family.id))

    search = request.args.get("q", "").strip()
    query = Family.query
    if current_user.has_role(*PARENT_ROLES):
        query = query.filter(Family.user_id == current_user.id)
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
    families_pagination = _paginate(query.order_by(Family.father_last_name.asc()))
    return render_template(
        "families.html",
        families=families_pagination.items,
        families_pagination=families_pagination,
        search_query=search,
    )


@main_bp.route("/families/<int:family_id>")
@login_required
def family_detail(family_id):
    family = Family.query.get_or_404(family_id)
    if not _family_access_allowed(family):
        abort(403)
    suggest_delete = request.args.get("suggest_delete") == "1"
    students_without_family = Student.query.filter_by(family_id=None).order_by(Student.last_name.asc()).all() if current_user.has_role(*ADMIN_ROLES) else []
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


@main_bp.route("/families/<int:family_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
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
    family.address_number = _optional_int(request.form.get("address_number"))
    family.street = request.form.get("street", "").strip() or None
    family.city = request.form.get("city", "").strip() or None
    family.zip_code = request.form.get("zip_code", "").strip() or None
    db.session.commit()
    flash("Famille mise à jour.", "success")
    return redirect(url_for("main.family_detail", family_id=family_id))


@main_bp.route("/families/<int:family_id>/students/add", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def family_add_student(family_id):
    family = Family.query.get_or_404(family_id)
    student_id = _optional_int(request.form.get("student_id"))
    if not student_id:
        flash("Sélectionnez un élève.", "warning")
        return redirect(url_for("main.family_detail", family_id=family_id))
    student = Student.query.get_or_404(student_id)
    student.family_id = family.id
    if any(enrollment.status == "active" for enrollment in student.enrollments):
        _ensure_family_payment_target(family)
    db.session.commit()
    flash(f"{student.first_name} {student.last_name} ajoute(e) a la famille.", "success")
    return redirect(url_for("main.family_detail", family_id=family_id))


@main_bp.route("/families/<int:family_id>/students/new", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def family_new_student(family_id):
    family = Family.query.get_or_404(family_id)
    try:
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        birth_date = request.form.get("birth_date", "").strip()
        site_id = _optional_int(request.form.get("site_id"))
        gender = request.form.get("gender", "").strip() or None
        is_reinscription = request.form.get("is_reinscription") == "1"

        if not all([first_name, last_name, birth_date]):
            flash("Prénom, nom et date de naissance sont obligatoires.", "warning")
            return redirect(url_for("main.family_detail", family_id=family_id))

        parsed_birth = _parse_date(birth_date)
        cutoff = date(date.today().year, 10, 1)
        if _age_on_cutoff(parsed_birth, cutoff) < 6:
            flash("L'élève doit avoir au moins 6 ans au 1er octobre de l'année en cours.", "warning")
            return redirect(url_for("main.family_detail", family_id=family_id))

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
    return redirect(url_for("main.family_detail", family_id=family_id))


@main_bp.route("/families/<int:family_id>/students/<int:student_id>/remove", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def family_remove_student(family_id, student_id):
    student = Student.query.get_or_404(student_id)
    family = Family.query.get_or_404(family_id)
    student.family_id = None
    db.session.flush()
    _ensure_family_payment_target(family)
    db.session.commit()
    flash("Élève retire de la famille.", "success")
    return redirect(url_for("main.family_detail", family_id=family_id))


@main_bp.route("/families/<int:family_id>/delete", methods=["POST"])
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
        return redirect(url_for("main.family_detail", family_id=family_id))

    for student in family.students:
        student.family_id = None

    for payment in family.payments:
        payment.family_id = None

    db.session.delete(family)
    db.session.commit()
    flash("Famille supprimée.", "success")
    return redirect(url_for("main.families_page"))


@main_bp.route("/families/<int:family_id>/set-parent", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
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
        return redirect(url_for("main.family_detail", family_id=family_id))

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()

    if not all([first_name, last_name, email, password]):
        flash("Prénom, nom, email et mot de passe sont obligatoires.", "warning")
        return redirect(url_for("main.family_detail", family_id=family_id))

    if family.user:
        user = family.user
        user.first_name = first_name
        user.last_name = last_name
        if email != user.email:
            if User.query.filter_by(email=email).first():
                flash("Cette adresse e-mail est déjà utilisee.", "warning")
                return redirect(url_for("main.family_detail", family_id=family_id))
            user.email = email
        if password:
            user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash("Compte parent mis à jour.", "success")
    else:
        user, error = _create_user(first_name, last_name, email, password, "parent")
        if error:
            db.session.rollback()
            flash(error, "warning")
            return redirect(url_for("main.family_detail", family_id=family_id))
        family.user_id = user.id
        db.session.commit()
        flash(f"Compte parent créé pour {first_name} {last_name}.", "success")

    return redirect(url_for("main.family_detail", family_id=family_id))


@main_bp.route("/payments", methods=["GET", "POST"])
@login_required
def payments_page():
    if not current_user.has_role(*ADMIN_ROLES, *PARENT_ROLES):
        abort(403)

    selected_family_id = _optional_int(request.args.get("family_id"))
    quick_flow = request.args.get("quick_flow") == "1"

    if request.method == "POST":
        if not current_user.has_role(*ADMIN_ROLES):
            abort(403)
        family_id = _optional_int(request.form.get("family_id"))
        total_amount = _optional_float(request.form.get("total_amount"))
        payment_date_raw = request.form.get("payment_date", "").strip()
        payment_date = _parse_date(payment_date_raw) if payment_date_raw else None
        method = request.form.get("method", "").strip() or None
        installments_count = _optional_int(request.form.get("installments_count"))
        quick_flow = request.form.get("quick_flow") == "1"

        if family_id and total_amount is None:
            family = Family.query.get(family_id)
            if family:
                total_amount = float(family.suggested_amount())

        if not family_id or total_amount is None:
            flash("Famille et montant sont obligatoires.", "warning")
            return redirect(url_for("main.payments_page", family_id=family_id, quick_flow=1 if quick_flow else None))

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
                due_date = _next_due_date(previous_due, 1)
                db.session.add(
                    PaymentInstallment(
                        payment=payment,
                        installment_number=idx,
                        amount=round(cents / 100, 2),
                        payment_date=due_date,
                        method=None,
                    )
                )
                previous_due = due_date

        db.session.commit()

        if quick_flow:
            flash("Paiement créé. Parcours d'inscription terminé.", "success")
            return redirect(url_for("main.family_detail", family_id=family_id))

        flash("Paiement créé.", "success")
        return redirect(url_for("main.payment_detail", payment_id=payment.id))

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
    payments_pagination = _paginate(query.order_by(Payment.payment_date.desc()))
    families = Family.query.order_by(Family.father_last_name.asc()).all() if current_user.has_role(*ADMIN_ROLES) else []
    default_total_amount = None
    if selected_family_id:
        selected_family = next((family for family in families if family.id == selected_family_id), None)
        if selected_family:
            default_total_amount = float(selected_family.suggested_amount())

    return render_template(
        "payments.html",
        payments=payments_pagination.items,
        payments_pagination=payments_pagination,
        families=families,
        default_total_amount=default_total_amount,
        search_query=search,
        selected_family_id=selected_family_id,
        quick_flow=quick_flow,
    )


@main_bp.route("/payments/<int:payment_id>")
@login_required
def payment_detail(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if not _family_access_allowed(payment.family):
        abort(403)
    return render_template("payment_detail.html", payment=payment, today=date.today().isoformat())


@main_bp.route("/payment-setup/<int:payment_id>", methods=["GET", "POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def payment_quick_setup(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if request.method == "POST":
        total_amount = _optional_float(request.form.get("total_amount"))
        payment_date_raw = request.form.get("payment_date", "").strip()
        payment_date = _parse_date(payment_date_raw) if payment_date_raw else date.today()
        installments_count = _optional_int(request.form.get("installments_count")) or 1

        if total_amount is None:
            flash("Le montant total est obligatoire.", "warning")
            return redirect(url_for("main.payment_quick_setup", payment_id=payment_id))

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
            due_date = payment_date if idx == 1 else _next_due_date(payment_date, idx - 1)

            custom_amount = _optional_float(request.form.get(f"inst_{idx}_amount"))
            custom_date_raw = request.form.get(f"inst_{idx}_date", "").strip()
            custom_date = _parse_date(custom_date_raw) if custom_date_raw else None
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
        return redirect(url_for("main.payment_detail", payment_id=payment.id))

    default_amount = float(payment.total_amount or (payment.family.suggested_amount() if payment.family else 0))
    return render_template(
        "payment_setup.html",
        payment=payment,
        default_amount=default_amount,
    )


@main_bp.route("/payments/<int:payment_id>/installments", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def add_installment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    installment_number = _optional_int(request.form.get("installment_number"))
    amount = _optional_float(request.form.get("amount"))
    method = request.form.get("method", "").strip() or None
    payment_date_raw = request.form.get("payment_date", "").strip()
    payment_date = _parse_date(payment_date_raw) if payment_date_raw else None
    if not installment_number or amount is None:
        flash("Numéro et montant de l'échéance sont obligatoires.", "warning")
        return redirect(url_for("main.payment_detail", payment_id=payment_id))
    paid_total = float(sum((i.amount or 0) for i in payment.installments if i.method))
    remaining = float(payment.total_amount or 0) - paid_total
    if method and amount > remaining + 0.01:
        flash("Montant trop élève: risque de trop-percu.", "warning")
        return redirect(url_for("main.payment_detail", payment_id=payment_id))
    existing = PaymentInstallment.query.filter_by(payment_id=payment_id, installment_number=installment_number).first()
    if existing:
        flash("Ce numero d'échéance existe déjà.", "warning")
        return redirect(url_for("main.payment_detail", payment_id=payment_id))
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
    return redirect(url_for("main.payment_detail", payment_id=payment_id))


@main_bp.route("/payments/<int:payment_id>/installments/<int:installment_id>/edit", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def edit_installment(payment_id, installment_id):
    payment = Payment.query.get_or_404(payment_id)
    installment = PaymentInstallment.query.filter_by(id=installment_id, payment_id=payment_id).first_or_404()

    new_amount = _optional_float(request.form.get("amount"))
    new_method = request.form.get("method", "").strip() or None
    payment_date_raw = request.form.get("payment_date", "").strip()
    new_payment_date = _parse_date(payment_date_raw) if payment_date_raw else installment.payment_date

    if new_amount is None:
        flash("Le montant est obligatoire.", "warning")
        return redirect(url_for("main.payment_detail", payment_id=payment_id))

    other_paid = float(sum((i.amount or 0) for i in payment.installments if i.id != installment.id and i.method))
    max_allowed = float(payment.total_amount or 0) - other_paid
    if new_method and new_amount > max_allowed + 0.01:
        flash("Montant invalide: trop-percu detecte.", "warning")
        return redirect(url_for("main.payment_detail", payment_id=payment_id))

    installment.amount = new_amount
    installment.method = new_method
    installment.payment_date = new_payment_date
    db.session.commit()
    flash("Echeance mise à jour.", "success")
    return redirect(url_for("main.payment_detail", payment_id=payment_id))


@main_bp.route("/payments/<int:payment_id>/installments/<int:installment_id>/delete", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def delete_installment(payment_id, installment_id):
    installment = PaymentInstallment.query.filter_by(id=installment_id, payment_id=payment_id).first_or_404()
    db.session.delete(installment)
    db.session.commit()
    flash("Echeance supprimée.", "success")
    return redirect(url_for("main.payment_detail", payment_id=payment_id))


@main_bp.route("/payments/<int:payment_id>/delete", methods=["POST"])
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
            return redirect(url_for("main.payment_detail", payment_id=payment.id))

    db.session.delete(payment)
    db.session.commit()
    flash("Paiement supprime.", "success")
    return redirect(url_for("main.payments_page"))


@main_bp.route("/exports/<string:dataset>.csv")
@login_required
@roles_required(*ADMIN_ROLES)
def export_csv(dataset):
    output = io.StringIO()
    writer = csv.writer(output)

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


@main_bp.route("/documents/payments/<int:payment_id>.pdf")
@login_required
def payment_receipt_pdf(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if not _family_access_allowed(payment.family):
        abort(403)

    preset_name, preset = _get_pdf_preset()

    def draw(pdf, width, height):
        margin = preset["margin_mm"] * mm
        pdf.setTitle(f"Reçu de paiement – {payment.family.display_name if payment.family else ''}")
        y = _pdf_draw_header(pdf, width, height, preset)

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
        payment_date_str = payment.payment_date.strftime("%d/%m/%Y") if payment.payment_date else "Non renseignée"
        issue_date_str = date.today().strftime("%d/%m/%Y")
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
                    inst.payment_date.strftime("%d/%m/%Y") if inst.payment_date else "—",
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
            f"Document généré le {issue_date_str} – {_ASSO_NAME} – style {preset_name}",
        )
        pdf.setFillColorRGB(0, 0, 0)

    return _render_pdf(f"reçu-paiement-{payment.id}.pdf", draw)


@main_bp.route("/documents/students/<int:student_id>/attestation.pdf")
@login_required
def student_certificate_pdf(student_id):
    student = Student.query.get_or_404(student_id)
    if not _student_access_allowed(student):
        abort(403)

    preset_name, preset = _get_pdf_preset()

    active_courses = [enrollment.course for enrollment in student.enrollments if enrollment.status == "active"]
    school_year = student.family.school_year if student.family and student.family.school_year else f"{date.today().year}-{date.today().year + 1}"
    level = next((course.level for course in active_courses if course and course.level), None) or "sans_niveau"

    def draw(pdf, width, height):
        margin = preset["margin_mm"] * mm
        issue_date_str = date.today().strftime("%d/%m/%Y")
        pdf.setTitle(f"Attestation d'inscription – {student.full_name}")
        y = _pdf_draw_header(pdf, width, height, preset)

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
        birth_str = student.birth_date.strftime("%d/%m/%Y") if student.birth_date else "Non renseignée"
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
            f"Document généré le {issue_date_str} – {_ASSO_NAME} – style {preset_name}",
        )
        pdf.setFillColorRGB(0, 0, 0)

    filename = (
        f"{_filename_token(student.last_name)}_"
        f"{_filename_token(student.first_name)}_"
        f"{_filename_token(school_year)}_"
        f"{_filename_token(level)}.pdf"
    )
    return _render_pdf(filename, draw)


# ── Teacher portal ────────────────────────────────────────────────────────────

def _get_teacher_or_403():
    """Return the Teacher linked to the current user, or abort 403."""
    teacher = current_user.teacher
    if teacher is None:
        abort(403)
    return teacher


@main_bp.route("/teacher/my-classes")
@login_required
@roles_required(*PEDAGOGY_ROLES)
def teacher_my_classes():
    if current_user.has_role("teacher"):
        teacher = _get_teacher_or_403()
        courses = sorted(teacher.courses, key=lambda c: (c.day or "", c.start_hour or 0))
    else:
        courses = Course.query.order_by(Course.title.asc()).all()
    return render_template("teacher_my_classes.html", courses=courses)


@main_bp.route("/teacher/courses/<int:course_id>")
@login_required
@roles_required(*PEDAGOGY_ROLES)
def teacher_course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    if current_user.has_role("teacher"):
        teacher = _get_teacher_or_403()
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


@main_bp.route("/teacher/courses/<int:course_id>/assessment", methods=["POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def teacher_add_assessment(course_id):
    course = Course.query.get_or_404(course_id)
    if current_user.has_role("teacher"):
        teacher = _get_teacher_or_403()
        if course.teacher_id != teacher.id:
            abort(403)
    try:
        assessment = StudentAssessment(
            student_id=_optional_int(request.form.get("student_id")),
            course_id=course_id,
            assessment_date=_parse_date(request.form.get("assessment_date")) if request.form.get("assessment_date") else date.today(),
            category=request.form.get("category", "").strip() or "Contrôle continu",
            score=_optional_float(request.form.get("score")),
            max_score=_optional_float(request.form.get("max_score")) or 20,
            appreciation=request.form.get("appreciation", "").strip() or None,
        )
        db.session.add(assessment)
        db.session.commit()
        flash("Évaluation enregistrée.", "success")
    except (ValueError, IntegrityError):
        db.session.rollback()
        flash("Impossible d'enregistrer cette évaluation.", "danger")
    return redirect(url_for("main.teacher_course_detail", course_id=course_id))


@main_bp.route("/teacher/courses/<int:course_id>/assessment/<int:assessment_id>/delete", methods=["POST"])
@login_required
@roles_required(*PEDAGOGY_ROLES)
def teacher_delete_assessment(course_id, assessment_id):
    course = Course.query.get_or_404(course_id)
    if current_user.has_role("teacher"):
        teacher = _get_teacher_or_403()
        if course.teacher_id != teacher.id:
            abort(403)
    assessment = StudentAssessment.query.get_or_404(assessment_id)
    db.session.delete(assessment)
    db.session.commit()
    flash("Évaluation supprimée.", "success")
    return redirect(url_for("main.teacher_course_detail", course_id=course_id))


@main_bp.route("/admin/bootstrap", methods=["POST"])
def bootstrap_admin():
    if not current_app.config.get("ENABLE_BOOTSTRAP_ENDPOINT", False):
        return jsonify({"error": "not_found"}), 404

    expected_token = current_app.config.get("BOOTSTRAP_TOKEN", "")
    provided_token = request.headers.get("X-Bootstrap-Token", "")
    if not expected_token or provided_token != expected_token:
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    admin_email = payload.get("admin_email", "admin@edumanager.local")
    admin_password = payload.get("admin_password", "ChangeMe123!")
    admin_first_name = payload.get("admin_first_name", "Admin")
    admin_last_name = payload.get("admin_last_name", "EduManager")

    result = seed_initial_data(
        admin_email=admin_email,
        admin_password=admin_password,
        admin_first_name=admin_first_name,
        admin_last_name=admin_last_name,
    )
    return jsonify(result), 200