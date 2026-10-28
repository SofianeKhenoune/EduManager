from datetime import date, timedelta

from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import extract, func

from app import db
from app.authz import OFFICE_ROLES, roles_required
from app.models import (
    Course,
    CourseSession,
    Employee,
    EmployeeLeaveRequest,
    Enrollment,
    Family,
    Payment,
    PaymentInstallment,
    Site,
    Student,
    StudentAssessment,
    Teacher,
)
from app.routes.helpers import default_home_endpoint_for

bp = Blueprint("dashboard", __name__)

@bp.app_errorhandler(403)
def forbidden(_error):
    return render_template("forbidden.html"), 403

@bp.route("/")
@login_required
def index():
    if not current_user.has_role(*OFFICE_ROLES):
        return redirect(url_for(default_home_endpoint_for(current_user)))
    
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


@bp.route("/api/dashboard")
@login_required
@roles_required(*OFFICE_ROLES)
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


@bp.route("/api/kpis")
@login_required
@roles_required(*OFFICE_ROLES)
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

