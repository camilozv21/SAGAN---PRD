import enum
from datetime import datetime

from sqlalchemy.orm import validates

from app import db


class PersonRole(enum.Enum):
    CLIENT_1 = "client_1"
    CLIENT_2 = "client_2"


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    property_address = db.Column(db.String(255), nullable=True)
    transfer_day_of_month = db.Column(db.Integer, nullable=False, default=28)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    people = db.relationship(
        "Person",
        backref="client",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Person.role",
    )
    accounts = db.relationship(
        "Account",
        backref="client",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    liabilities = db.relationship(
        "Liability",
        backref="client",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    insurance_policies = db.relationship(
        "InsurancePolicy",
        backref="client",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    static_financials = db.relationship(
        "StaticFinancials",
        backref="client",
        cascade="all, delete-orphan",
        uselist=False,
    )
    quarterly_reports = db.relationship(
        "QuarterlyReport",
        backref="client",
        cascade="all, delete-orphan",
    )

    @validates("transfer_day_of_month")
    def _validate_day(self, key, value):
        if value is None or not (1 <= int(value) <= 31):
            raise ValueError("transfer_day_of_month must be between 1 and 31")
        return int(value)

    def person(self, role):
        """Devuelve la Person con el role indicado, o None si no existe."""
        target = role if isinstance(role, PersonRole) else PersonRole(role)
        return next((p for p in self.people if p.role == target), None)

    @property
    def is_married(self):
        return self.person(PersonRole.CLIENT_2) is not None


class Person(db.Model):
    __tablename__ = "people"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = db.Column(
        db.Enum(PersonRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    name = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.Date, nullable=True)
    ssn_last_4 = db.Column(db.String(4), nullable=True)
    monthly_salary = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("client_id", "role", name="uq_person_client_role"),
    )

    @validates("ssn_last_4")
    def _validate_ssn(self, key, value):
        if value is None or value == "":
            return None
        if not (isinstance(value, str) and len(value) == 4 and value.isdigit()):
            raise ValueError("ssn_last_4 must be exactly 4 digits")
        return value

    @validates("monthly_salary")
    def _validate_salary(self, key, value):
        if value is not None and float(value) < 0:
            raise ValueError("monthly_salary must be >= 0")
        return value


class StaticFinancials(db.Model):
    __tablename__ = "static_financials"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    agreed_monthly_outflow = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    private_reserve_target_override = db.Column(db.Numeric(12, 2), nullable=True)

    @validates("agreed_monthly_outflow", "private_reserve_target_override")
    def _validate_non_negative(self, key, value):
        if value is not None and float(value) < 0:
            raise ValueError(f"{key} must be >= 0")
        return value
