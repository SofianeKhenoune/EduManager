from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.authz import ADMIN_ROLES, roles_required
from app.models import Site
from app.routes.helpers import paginate

bp = Blueprint("sites", __name__)

@bp.route("/sites", methods=["GET", "POST"])
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
        return redirect(url_for("sites.sites_page"))
    sites_pagination = paginate(Site.query.order_by(Site.name.asc()))
    return render_template("sites.html", sites=sites_pagination.items, sites_pagination=sites_pagination)


@bp.route("/sites/<int:site_id>/edit", methods=["POST"])
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
    return redirect(url_for("sites.sites_page"))


@bp.route("/sites/<int:site_id>/delete", methods=["POST"])
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
    return redirect(url_for("sites.sites_page"))

