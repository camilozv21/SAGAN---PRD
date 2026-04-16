from datetime import datetime

from app import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("quarterly_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = db.Column(db.String(60), nullable=False)
    detail = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", backref="audit_logs")
    report = db.relationship("QuarterlyReport", backref="audit_logs")
