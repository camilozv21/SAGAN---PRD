from datetime import datetime

from app import db


class QuarterlyReport(db.Model):
    __tablename__ = "quarterly_reports"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_date = db.Column(db.Date, nullable=False)
    inflow_client_1_snapshot = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    inflow_client_2_snapshot = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    outflow_snapshot = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    trust_value_snapshot = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    target_snapshot = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    generated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    balances = db.relationship("AccountBalance", backref="report")
