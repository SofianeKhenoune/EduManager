from flask import Blueprint, render_template
from flask_login import login_required

from app.authz import roles_required

bp = Blueprint("student_portal", __name__)

@bp.route("/student/home")
@login_required
@roles_required("student")
def student_home():
    return render_template("student_home.html")
