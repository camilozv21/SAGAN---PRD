from sqlalchemy.orm import validates

from app import db


class Liability(db.Model):
    __tablename__ = "liabilities"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(120), nullable=False)
    interest_rate = db.Column(db.Numeric(6, 4), nullable=True)
    balance = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    as_of_date = db.Column(db.Date, nullable=True)

    @validates("balance")
    def _validate_balance(self, key, value):
        if value is not None and float(value) < 0:
            raise ValueError("balance must be >= 0")
        return value

    @validates("interest_rate")
    def _validate_rate(self, key, value):
        if value is not None and float(value) < 0:
            raise ValueError("interest_rate must be >= 0")
        return value


class InsurancePolicy(db.Model):
    __tablename__ = "insurance_policies"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    type = db.Column(db.String(60), nullable=False)
    deductible = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    @validates("deductible")
    def _validate_deductible(self, key, value):
        if value is not None and float(value) < 0:
            raise ValueError("deductible must be >= 0")
        return value
