from datetime import date

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint, text

from app import db

# ── Grille tarifaire (cours d'arabe) ─────────────────────────
# clé : nb enfants actifs dans la famille (3 = 3 et plus)
TARIF_GRID = {
    "normal": {1: 320, 2: 290, 3: 260},
    "special": {1: 290, 2: 260, 3: 230},
}


def calc_tarif(tarif_type: str, nb_children: int) -> int:
    """Retourne le montant total attendu pour une famille."""
    if nb_children <= 0:
        return 0
    tier = min(nb_children, 3)
    return nb_children * TARIF_GRID.get(tarif_type, TARIF_GRID["normal"])[tier]


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, unique=True, nullable=False)

    users = db.relationship("User", back_populates="role", lazy=True)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.Text, nullable=False)
    last_name = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"))
    phone_number = db.Column(db.Text)

    role = db.relationship("Role", back_populates="users")
    teacher = db.relationship("Teacher", back_populates="user", uselist=False)
    family = db.relationship("Family", back_populates="user", uselist=False)
    employee = db.relationship("Employee", back_populates="user", uselist=False)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def role_name(self):
        return self.role.name if self.role else None

    def has_role(self, *role_names: str) -> bool:
        return self.role_name in role_names


class Teacher(db.Model):
    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    subject = db.Column(db.Text)

    user = db.relationship("User", back_populates="teacher")
    courses = db.relationship("Course", back_populates="teacher", lazy=True)

    @property
    def full_name(self):
        return self.user.full_name if self.user else ""


class Site(db.Model):
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False, unique=True)
    address = db.Column(db.Text)

    courses = db.relationship("Course", back_populates="site", lazy=True)
    students = db.relationship("Student", back_populates="site", lazy=True)


class Family(db.Model):
    __tablename__ = "families"
    __table_args__ = (
        CheckConstraint("tarif_type IN ('normal', 'special')", name="check_family_tarif_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, unique=True)
    school_year = db.Column(db.Text, nullable=False, server_default=text("'2025-2026'"))
    tarif_type = db.Column(db.Text, nullable=False, server_default=text("'normal'"))
    father_first_name = db.Column(db.Text)
    father_last_name = db.Column(db.Text)
    father_phone = db.Column(db.Text)
    father_email = db.Column(db.Text)
    mother_first_name = db.Column(db.Text)
    mother_last_name = db.Column(db.Text)
    mother_phone = db.Column(db.Text)
    mother_email = db.Column(db.Text)
    address_number = db.Column(db.Integer)
    street = db.Column(db.Text)
    city = db.Column(db.Text)
    zip_code = db.Column(db.Text)

    students = db.relationship("Student", back_populates="family", lazy=True)
    payments = db.relationship("Payment", back_populates="family", lazy=True)
    user = db.relationship("User", back_populates="family", uselist=False)

    @property
    def display_name(self):
        last = self.father_last_name or self.mother_last_name
        if last:
            return f"Famille {last}"
        if self.students:
            return f"Famille {self.students[0].last_name}"
        return f"Famille #{self.id}"

    @property
    def active_children_count(self):
        return sum(1 for student in self.students if any(enrollment.status == "active" for enrollment in student.enrollments))

    @property
    def total_paid(self):
        return float(sum((payment.total_amount or 0) for payment in self.payments))

    def suggested_amount(self):
        return calc_tarif(self.tarif_type, self.active_children_count)


class Course(db.Model):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("time_slot IN ('matin', 'après-midi')", name="check_time_slot"),
        CheckConstraint(
            "day IN ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')",
            name="check_day",
        ),
        CheckConstraint(
            "level IN ('PREPA', 'NIV1', 'NIV2', 'NIV3', 'NIV4', 'NIV5', 'NIV6', 'NIV7')",
            name="check_level",
        ),
        CheckConstraint("start_hour BETWEEN 0 AND 23", name="check_start_hour"),
        CheckConstraint("end_hour BETWEEN 0 AND 23", name="check_end_hour"),
        CheckConstraint("end_hour > start_hour", name="check_hours_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"))
    level = db.Column(db.Text)
    day = db.Column(db.Text)
    time_slot = db.Column(db.Text)
    start_hour = db.Column(db.Integer)
    end_hour = db.Column(db.Integer)
    room = db.Column(db.Text)
    capacity = db.Column(db.Integer, nullable=False, server_default=text("20"))

    teacher = db.relationship("Teacher", back_populates="courses")
    site = db.relationship("Site", back_populates="courses")
    enrollments = db.relationship("Enrollment", back_populates="course", lazy=True)
    sessions = db.relationship("CourseSession", back_populates="course", lazy=True, cascade="all, delete-orphan")
    assessments = db.relationship("StudentAssessment", back_populates="course", lazy=True)

    @property
    def active_enrollments_count(self):
        return sum(1 for enrollment in self.enrollments if enrollment.status == "active")

    @property
    def occupancy_rate(self):
        if not self.capacity:
            return 0
        return round((self.active_enrollments_count / self.capacity) * 100, 1)

    @property
    def schedule_label(self):
        if self.day and self.start_hour is not None and self.end_hour is not None:
            return f"{self.day.capitalize()} {self.start_hour:02d}h-{self.end_hour:02d}h"
        return "Non planifie"


class Student(db.Model):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("gender IN ('M', 'F')", name="check_student_gender"),
    )

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.Text, nullable=False)
    last_name = db.Column(db.Text, nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"))
    family_id = db.Column(db.Integer, db.ForeignKey("families.id"))
    gender = db.Column(db.Text)
    is_reinscription = db.Column(db.Boolean, server_default=text("false"), nullable=False)
    birth_date = db.Column(db.Date, nullable=False)
    lives_alone = db.Column(db.Boolean, server_default=text("false"), nullable=False)

    site = db.relationship("Site", back_populates="students")
    family = db.relationship("Family", back_populates="students")
    enrollments = db.relationship("Enrollment", back_populates="student", lazy=True)
    attendance_records = db.relationship("AttendanceRecord", back_populates="student", lazy=True, cascade="all, delete-orphan")
    assessments = db.relationship("StudentAssessment", back_populates="student", lazy=True, cascade="all, delete-orphan")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def age(self):
        if self.birth_date is None:
            return None
        today = date.today()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    @property
    def active_courses_count(self):
        return sum(1 for enrollment in self.enrollments if enrollment.status == "active")


class Enrollment(db.Model):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="unique_enrollment"),
        CheckConstraint("status IN ('active', 'annulee', 'en_attente')", name="check_enrollment_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    enrollment_date = db.Column(db.Date, nullable=False, server_default=text("CURRENT_DATE"))
    status = db.Column(db.Text)

    student = db.relationship("Student", back_populates="enrollments")
    course = db.relationship("Course", back_populates="enrollments")


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("method IN ('CB', 'ESP', 'CHQ')", name="check_payment_method"),
    )

    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey("families.id"))
    total_amount = db.Column(db.Numeric(10, 2))
    payment_date = db.Column(db.Date)
    method = db.Column(db.Text)

    family = db.relationship("Family", back_populates="payments")
    installments = db.relationship("PaymentInstallment", back_populates="payment", lazy=True, cascade="all, delete-orphan")

    @property
    def installments_total(self):
        return round(float(sum((installment.amount or 0) for installment in self.installments if installment.method)), 2)

    @property
    def remaining_amount(self):
        total_amount = round(float(self.total_amount or 0), 2)
        return round(total_amount - self.installments_total, 2)

    @property
    def progress_percent(self):
        total_amount = round(float(self.total_amount or 0), 2)
        if total_amount <= 0:
            return 0
        return min(int((self.installments_total / total_amount) * 100), 100)


class PaymentInstallment(db.Model):
    __tablename__ = "payments_n"
    __table_args__ = (
        UniqueConstraint("payment_id", "installment_number", name="unique_installment_number"),
        CheckConstraint("installment_number BETWEEN 1 AND 6", name="check_installment_number"),
        CheckConstraint("method IN ('CB', 'ESP', 'CHQ')", name="check_payment_n_method"),
    )

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"))
    installment_number = db.Column(db.Integer)
    amount = db.Column(db.Numeric(10, 2))
    payment_date = db.Column(db.Date)
    method = db.Column(db.Text)

    payment = db.relationship("Payment", back_populates="installments")


class Position(db.Model):
    __tablename__ = "positions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False, unique=True)
    description = db.Column(db.Text)

    employees = db.relationship("Employee", back_populates="position", lazy=True)


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False, unique=True)
    manager_id = db.Column(db.Integer, db.ForeignKey("employees.id"))

    employees = db.relationship(
        "Employee",
        foreign_keys="Employee.department_id",
        back_populates="department",
        lazy=True,
    )
    manager = db.relationship(
        "Employee",
        foreign_keys=[manager_id],
        back_populates="managed_department",
        uselist=False,
    )


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    hire_date = db.Column(db.Date, nullable=False)
    employee_id = db.Column(db.Text, nullable=False, unique=True)
    social_security_number = db.Column(db.Text, unique=True)
    contract_end_date = db.Column(db.Date)
    position_id = db.Column(db.Integer, db.ForeignKey("positions.id"))
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    birth_name = db.Column(db.Text)
    birth_date = db.Column(db.Date)
    birth_place = db.Column(db.Text)
    nationality = db.Column(db.Text)
    civility = db.Column(db.Text)
    address = db.Column(db.Text)
    zip_code = db.Column(db.Text)
    city = db.Column(db.Text)
    contract_type = db.Column(db.Text)
    trial_period_end = db.Column(db.Date)
    contract_duration = db.Column(db.Integer)
    level = db.Column(db.Text)
    index_grade = db.Column(db.Text)
    hours_per_week = db.Column(db.Float)
    hours_per_month = db.Column(db.Float)
    hourly_rate = db.Column(db.Float)
    monthly_salary = db.Column(db.Float)
    navigo_pass = db.Column(db.Boolean, default=False)
    pas_rate = db.Column(db.Float)

    user = db.relationship("User", back_populates="employee")
    position = db.relationship("Position", back_populates="employees")
    department = db.relationship(
        "Department",
        foreign_keys=[department_id],
        back_populates="employees",
    )
    managed_department = db.relationship(
        "Department",
        foreign_keys="Department.manager_id",
        back_populates="manager",
        uselist=False,
    )
    salary_details = db.relationship("SalaryDetail", back_populates="employee", lazy=True, cascade="all, delete-orphan")
    performance_reviews = db.relationship("PerformanceReview", back_populates="employee", lazy=True, cascade="all, delete-orphan")
    leave_requests = db.relationship("EmployeeLeaveRequest", back_populates="employee", lazy=True, cascade="all, delete-orphan")

    @property
    def full_name(self):
        return self.user.full_name if self.user else ""

    @property
    def active_leave_count(self):
        return sum(1 for leave_request in self.leave_requests if leave_request.status == "approved")

    @property
    def latest_salary_detail(self):
        if not self.salary_details:
            return None
        return sorted(self.salary_details, key=lambda detail: detail.effective_date or date.min, reverse=True)[0]


class SalaryDetail(db.Model):
    __tablename__ = "salary_details"
    __table_args__ = (
        CheckConstraint("annual_salary >= 0", name="check_annual_salary_positive"),
        CheckConstraint("hourly_rate >= 0", name="check_hourly_rate_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    contract_type = db.Column(db.Text, nullable=False)
    hourly_rate = db.Column(db.Float)
    annual_salary = db.Column(db.Float)
    benefits = db.Column(db.Text)
    effective_date = db.Column(db.Date, nullable=False, server_default=text("CURRENT_DATE"))
    notes = db.Column(db.Text)

    employee = db.relationship("Employee", back_populates="salary_details")


class PerformanceReview(db.Model):
    __tablename__ = "performance_reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="check_review_rating"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    review_date = db.Column(db.Date, nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comments = db.Column(db.Text)
    goals = db.Column(db.Text)

    employee = db.relationship("Employee", back_populates="performance_reviews")


class EmployeeLeaveRequest(db.Model):
    __tablename__ = "employee_leave_requests"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="check_leave_dates"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="check_leave_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, server_default=text("'pending'"))
    comments = db.Column(db.Text)

    employee = db.relationship("Employee", back_populates="leave_requests")

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1


class CourseSession(db.Model):
    __tablename__ = "course_sessions"
    __table_args__ = (
        UniqueConstraint("course_id", "session_date", name="unique_course_session"),
        CheckConstraint("status IN ('planned', 'completed', 'cancelled')", name="check_session_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    topic = db.Column(db.Text)
    notes = db.Column(db.Text)
    status = db.Column(db.Text, nullable=False, server_default=text("'planned'"))

    course = db.relationship("Course", back_populates="sessions")
    attendance_records = db.relationship("AttendanceRecord", back_populates="session", lazy=True, cascade="all, delete-orphan")


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="unique_student_attendance"),
        CheckConstraint("status IN ('present', 'absent', 'late', 'excused')", name="check_attendance_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("course_sessions.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    status = db.Column(db.Text, nullable=False, server_default=text("'present'"))
    comment = db.Column(db.Text)

    session = db.relationship("CourseSession", back_populates="attendance_records")
    student = db.relationship("Student", back_populates="attendance_records")


class StudentAssessment(db.Model):
    __tablename__ = "student_assessments"
    __table_args__ = (
        CheckConstraint("max_score > 0", name="check_assessment_max_score"),
        CheckConstraint("score >= 0", name="check_assessment_score"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"))
    assessment_date = db.Column(db.Date, nullable=False, server_default=text("CURRENT_DATE"))
    category = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float)
    max_score = db.Column(db.Float, nullable=False, server_default=text("20"))
    appreciation = db.Column(db.Text)

    student = db.relationship("Student", back_populates="assessments")
    course = db.relationship("Course", back_populates="assessments")

    @property
    def percentage(self):
        if not self.max_score or self.score is None:
            return None
        return round((self.score / self.max_score) * 100, 1)
