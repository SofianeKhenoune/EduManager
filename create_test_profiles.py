from datetime import date

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import Family, Role, Teacher, User


PROFILES = [
    {
        "role": "admin",
        "first_name": "Admin",
        "last_name": "Test",
        "email": "admin.test@edumanager.local",
        "password": "AdminTest123!",
    },
    {
        "role": "staff",
        "first_name": "Staff",
        "last_name": "Test",
        "email": "staff.test@edumanager.local",
        "password": "StaffTest123!",
    },
    {
        "role": "manager",
        "first_name": "Manager",
        "last_name": "Test",
        "email": "manager.test@edumanager.local",
        "password": "ManagerTest123!",
    },
    {
        "role": "teacher",
        "first_name": "Teacher",
        "last_name": "Test",
        "email": "teacher.test@edumanager.local",
        "password": "TeacherTest123!",
    },
    {
        "role": "parent",
        "first_name": "Parent",
        "last_name": "Test",
        "email": "parent.test@edumanager.local",
        "password": "ParentTest123!",
    },
]


def default_school_year(today: date | None = None) -> str:
    current = today or date.today()
    if current.month >= 6:
        return f"{current.year}-{current.year + 1}"
    return f"{current.year - 1}-{current.year}"


def ensure_role(role_name: str) -> Role:
    role = Role.query.filter_by(name=role_name).first()
    if role is None:
        role = Role(name=role_name)
        db.session.add(role)
        db.session.flush()
    return role


def ensure_user(profile: dict) -> User:
    role = ensure_role(profile["role"])
    user = User.query.filter_by(email=profile["email"]).first()
    if user is None:
        user = User(
            first_name=profile["first_name"],
            last_name=profile["last_name"],
            email=profile["email"],
            password_hash=generate_password_hash(profile["password"]),
            role_id=role.id,
        )
        db.session.add(user)
        db.session.flush()
        return user

    user.first_name = profile["first_name"]
    user.last_name = profile["last_name"]
    user.role_id = role.id
    user.password_hash = generate_password_hash(profile["password"])
    db.session.flush()
    return user


def ensure_teacher_profile(user: User) -> None:
    teacher = Teacher.query.filter_by(user_id=user.id).first()
    if teacher is None:
        db.session.add(Teacher(user_id=user.id, subject="Test"))


def ensure_parent_profile(user: User) -> None:
    family = Family.query.filter_by(user_id=user.id).first()
    if family is not None:
        family.father_email = user.email
        family.father_first_name = family.father_first_name or user.first_name
        family.father_last_name = family.father_last_name or user.last_name
        return

    fallback_family = Family.query.filter_by(father_email=user.email).first()
    if fallback_family is not None and fallback_family.user_id is None:
        fallback_family.user_id = user.id
        fallback_family.father_first_name = fallback_family.father_first_name or user.first_name
        fallback_family.father_last_name = fallback_family.father_last_name or user.last_name
        fallback_family.school_year = fallback_family.school_year or default_school_year()
        fallback_family.tarif_type = fallback_family.tarif_type or "normal"
        return

    db.session.add(
        Family(
            user_id=user.id,
            school_year=default_school_year(),
            tarif_type="normal",
            father_first_name=user.first_name,
            father_last_name=user.last_name,
            father_email=user.email,
            city="Testville",
            zip_code="75001",
            street="1 rue de test",
        )
    )


def main() -> None:
    app = create_app()
    with app.app_context():
        created_or_updated = []

        for profile in PROFILES:
            user = ensure_user(profile)
            if profile["role"] == "teacher":
                ensure_teacher_profile(user)
            if profile["role"] == "parent":
                ensure_parent_profile(user)
            created_or_updated.append(profile)

        db.session.commit()

        print("Comptes de test prêts :")
        for p in created_or_updated:
            print(f"- {p['role']}: {p['email']} / {p['password']}")


if __name__ == "__main__":
    main()
