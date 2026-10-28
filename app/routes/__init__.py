from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.routes.auth import bp as auth_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.students import bp as students_bp
    from app.routes.families import bp as families_bp
    from app.routes.enrollments import bp as enrollments_bp
    from app.routes.courses import bp as courses_bp
    from app.routes.assessments import bp as assessments_bp
    from app.routes.teachers_portal import bp as teachers_portal_bp
    from app.routes.teachers_admin import bp as teachers_admin_bp
    from app.routes.employees import bp as employees_bp
    from app.routes.sites import bp as sites_bp
    from app.routes.payments import bp as payments_bp
    from app.routes.documents import bp as documents_bp
    from app.routes.student_portal import bp as student_portal_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(families_bp)
    app.register_blueprint(enrollments_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(teachers_portal_bp)
    app.register_blueprint(teachers_admin_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(sites_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(student_portal_bp)
