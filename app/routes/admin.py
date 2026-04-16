"""Admin routes (Phase 6): audit log viewer.

Access restricted to users with is_admin=True.
"""
from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.models import AuditLog

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    if not current_user.is_admin:
        abort(403)


@admin_bp.route("/audit")
@login_required
def audit_log():
    _require_admin()
    logs = (
        AuditLog.query
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template("admin/audit.html", logs=logs)
