from datetime import date
from typing import Dict, List

from werkzeug.security import generate_password_hash

from app import db
from app.models import Course, Enrollment, Family, Role, Site, Student, Teacher, User


DEFAULT_ROLES: List[str] = [
    "admin",
    "teacher",
    "student",
    "staff",
    "manager",
    "volunteer",
    "parent",
]


def _ensure_default_roles() -> int:
    created_roles = 0

    for role_name in DEFAULT_ROLES:
        role = Role.query.filter_by(name=role_name).first()
        if role is None:
            db.session.add(Role(name=role_name))
            created_roles += 1

    return created_roles


def _get_role_id(name: str) -> int:
    role = Role.query.filter_by(name=name).first()
    if role is None:
        role = Role(name=name)
        db.session.add(role)
        db.session.flush()
    return role.id


def seed_initial_data(
    admin_email: str,
    admin_password: str,
    admin_first_name: str = "Admin",
    admin_last_name: str = "EduManager",
) -> Dict[str, object]:
    created_roles = _ensure_default_roles()

    db.session.flush()
    admin_role_id = _get_role_id("admin")

    admin_user = User.query.filter_by(email=admin_email).first()
    admin_created = False

    if admin_user is None:
        admin_user = User(
            first_name=admin_first_name,
            last_name=admin_last_name,
            email=admin_email,
            password_hash=generate_password_hash(admin_password),
            role_id=admin_role_id,
        )
        db.session.add(admin_user)
        admin_created = True
    else:
        admin_user.role_id = admin_role_id
        if not admin_user.password_hash:
            admin_user.password_hash = generate_password_hash(admin_password)

    db.session.commit()

    return {
        "created_roles": created_roles,
        "admin_created": admin_created,
        "admin_email": admin_email,
    }


def seed_demo_data() -> Dict[str, object]:
    created_roles = _ensure_default_roles()
    db.session.flush()

    teacher_role_id = _get_role_id("teacher")
    created = {
        "roles_created": created_roles,
        "site_created": False,
        "teacher_created": False,
        "student_created": False,
        "course_created": False,
        "enrollment_created": False,
    }

    site = Site.query.filter_by(name="Site Central").first()
    if site is None:
        site = Site(name="Site Central", address="10 Rue de l'Ecole")
        db.session.add(site)
        db.session.flush()
        created["site_created"] = True

    teacher_user = User.query.filter_by(email="teacher.demo@edumanager.local").first()
    if teacher_user is None:
        teacher_user = User(
            first_name="Amina",
            last_name="Prof",
            email="teacher.demo@edumanager.local",
            password_hash=generate_password_hash("Teacher123!"),
            role_id=teacher_role_id,
        )
        db.session.add(teacher_user)
        db.session.flush()
        created["teacher_created"] = True
    else:
        teacher_user.role_id = teacher_role_id

    teacher = Teacher.query.filter_by(user_id=teacher_user.id).first()
    if teacher is None:
        teacher = Teacher(user_id=teacher_user.id, subject="Mathematiques")
        db.session.add(teacher)
        db.session.flush()
        created["teacher_created"] = True

    family = Family.query.filter_by(father_last_name="Demo").first()
    if family is None:
        family = Family(
            school_year="2025-2026",
            tarif_type="normal",
            father_first_name="Karim",
            father_last_name="Demo",
            father_phone="0600000000",
            father_email="parent.demo@edumanager.local",
            city="Paris",
            zip_code="75010",
            street="5 Avenue des Arts",
        )
        db.session.add(family)
        db.session.flush()

    student = Student.query.filter_by(first_name="Youssef", last_name="Eleve").first()
    if student is None:
        student = Student(
            first_name="Youssef",
            last_name="Eleve",
            site_id=site.id,
            family_id=family.id,
            gender="M",
            birth_date=date(2011, 5, 20),
            lives_alone=False,
        )
        db.session.add(student)
        db.session.flush()
        created["student_created"] = True

    course = Course.query.filter_by(title="Maths Niveau 1", teacher_id=teacher.id).first()
    if course is None:
        course = Course(
            title="Maths Niveau 1",
            description="Cours demo pour bootstrap du projet",
            teacher_id=teacher.id,
            site_id=site.id,
            level="NIV1",
            day="lundi",
            time_slot="matin",
            start_hour=9,
            end_hour=11,
        )
        db.session.add(course)
        db.session.flush()
        created["course_created"] = True

    enrollment = Enrollment.query.filter_by(student_id=student.id, course_id=course.id).first()
    if enrollment is None:
        enrollment = Enrollment(student_id=student.id, course_id=course.id, status="active")
        db.session.add(enrollment)
        created["enrollment_created"] = True

    db.session.commit()
    return created
