import hmac

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app import csrf
from app.routes.helpers import default_home_endpoint_for
from app.models import User
from app.seed import seed_initial_data

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(default_home_endpoint_for(current_user)))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session.permanent = True
            login_user(user, remember=request.form.get("remember") == "1")
            next_page = request.args.get("next")
            return redirect(next_page or url_for(default_home_endpoint_for(user)))
        flash("Email ou mot de passe incorrect.", "danger")
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/health")
@csrf.exempt
def health():
    return jsonify({"status": "ok"}), 200


@bp.route("/admin/bootstrap", methods=["POST"])
@csrf.exempt
def bootstrap_admin():
    if not current_app.config.get("ENABLE_BOOTSTRAP_ENDPOINT", False):
        return jsonify({"error": "not_found"}), 404

    expected_token = current_app.config.get("BOOTSTRAP_TOKEN", "")
    provided_token = request.headers.get("X-Bootstrap-Token", "")
    if (
        not expected_token
        or not provided_token
        or not hmac.compare_digest(str(expected_token), str(provided_token))
    ):
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