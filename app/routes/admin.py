"""Admin routes (Phase 6): audit log viewer.

Access restricted to users with is_admin=True.
Currently auth is not fully wired (Phase 7), so the admin check
reads from session['user_id'] if present.
"""
from flask import Blueprint, abort, render_template, session

from app.models import AuditLog, User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return User.query.get(uid)


def _require_admin():
    user = _current_user()
    if user is None or not user.is_admin:
        abort(403)
    return user


@admin_bp.route("/audit")
def audit_log():
    _require_admin()
    page = max(1, int(session.get("audit_page", 1)))
    logs = (
        AuditLog.query
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template("admin/audit.html", logs=logs)
