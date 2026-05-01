from sqlalchemy import CheckConstraint, UniqueConstraint, text

from app import db


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, unique=True, nullable=False)

    users = db.relationship("User", back_populates="role", lazy=True)


class User(db.Model):
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
    student = db.relationship("Student", back_populates="user", uselist=False)
    employee = db.relationship("Employee", back_populates="user", uselist=False)


class Teacher(db.Model):
    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    subject = db.Column(db.Text)

    user = db.relationship("User", back_populates="teacher")
    courses = db.relationship("Course", back_populates="teacher", lazy=True)


class Site(db.Model):
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False, unique=True)
    address = db.Column(db.Text)

    courses = db.relationship("Course", back_populates="site", lazy=True)
    students = db.relationship("Student", back_populates="site", lazy=True)


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

    teacher = db.relationship("Teacher", back_populates="courses")
    site = db.relationship("Site", back_populates="courses")
    enrollments = db.relationship("Enrollment", back_populates="course", lazy=True)


class Student(db.Model):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("address_number >= 0", name="check_address_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"))
    father_first_name = db.Column(db.Text)
    father_last_name = db.Column(db.Text)
    father_email = db.Column(db.Text)
    father_phone = db.Column(db.Text)
    mother_first_name = db.Column(db.Text)
    mother_last_name = db.Column(db.Text)
    mother_email = db.Column(db.Text)
    mother_phone = db.Column(db.Text)
    address_number = db.Column(db.Integer)
    street = db.Column(db.Text, nullable=False)
    city = db.Column(db.Text, nullable=False)
    zip_code = db.Column(db.Text, nullable=False)
    birth_date = db.Column(db.Date, nullable=False)
    lives_alone = db.Column(db.Boolean, server_default=text("false"), nullable=False)

    user = db.relationship("User", back_populates="student")
    site = db.relationship("Site", back_populates="students")
    enrollments = db.relationship("Enrollment", back_populates="student", lazy=True)
    payments = db.relationship("Payment", back_populates="student", lazy=True)


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
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))
    total_amount = db.Column(db.Numeric(10, 2))
    payment_date = db.Column(db.Date)
    method = db.Column(db.Text)

    student = db.relationship("Student", back_populates="payments")
    installments = db.relationship("PaymentInstallment", back_populates="payment", lazy=True)


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
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)

    employees = db.relationship("Employee", back_populates="position", lazy=True)


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
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
    # Personal information
    birth_name = db.Column(db.Text)
    birth_date = db.Column(db.Date)
    birth_place = db.Column(db.Text)
    nationality = db.Column(db.Text)
    civility = db.Column(db.Text)
    # Address
    address = db.Column(db.Text)
    zip_code = db.Column(db.Text)
    city = db.Column(db.Text)
    # Contract information
    contract_type = db.Column(db.Text)
    trial_period_end = db.Column(db.Date)
    contract_duration = db.Column(db.Integer)
    # Position details
    level = db.Column(db.Text)
    index_grade = db.Column(db.Text)
    # Hours and salary
    hours_per_week = db.Column(db.Float)
    hours_per_month = db.Column(db.Float)
    hourly_rate = db.Column(db.Float)
    monthly_salary = db.Column(db.Float)
    # Benefits
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
    salary_details = db.relationship("SalaryDetail", back_populates="employee", lazy=True)
    performance_reviews = db.relationship("PerformanceReview", back_populates="employee", lazy=True)
    leave_requests = db.relationship("EmployeeLeaveRequest", back_populates="employee", lazy=True)


class SalaryDetail(db.Model):
    __tablename__ = "salary_details"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    contract_type = db.Column(db.Text, nullable=False)
    hourly_rate = db.Column(db.Float)
    annual_salary = db.Column(db.Float)
    benefits = db.Column(db.Text)

    employee = db.relationship("Employee", back_populates="salary_details")


class PerformanceReview(db.Model):
    __tablename__ = "performance_reviews"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    review_date = db.Column(db.Date, nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comments = db.Column(db.Text)

    employee = db.relationship("Employee", back_populates="performance_reviews")


class EmployeeLeaveRequest(db.Model):
    __tablename__ = "employee_leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, server_default=text("'pending'"))
    comments = db.Column(db.Text)

    employee = db.relationship("Employee", back_populates="leave_requests")
