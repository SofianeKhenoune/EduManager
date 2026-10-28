from functools import wraps

from flask import abort, current_app
from flask_login import current_user

from app.models import Family, Student

ADMIN_ROLES = ("admin", "manager")
STAFF_ROLES = ("staff",)
OFFICE_ROLES = ADMIN_ROLES + STAFF_ROLES
PEDAGOGY_ROLES = OFFICE_ROLES + ("teacher", "volunteer")
PEDAGOGY_MUTATION_ROLES = OFFICE_ROLES + ("teacher",)
PARENT_ROLES = ("parent",)


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


def family_access_allowed(family: Family) -> bool:
    if current_user.has_role(*OFFICE_ROLES):
        return True
    return current_user.has_role(*PARENT_ROLES) and family.user_id == current_user.id


def student_access_allowed(student: Student) -> bool:
    if current_user.has_role(*OFFICE_ROLES, "teacher"):
        return True
    return (
        current_user.has_role(*PARENT_ROLES)
        and student.family
        and student.family.user_id == current_user.id
    )
