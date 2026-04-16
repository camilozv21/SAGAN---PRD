import enum
from datetime import datetime

from sqlalchemy.orm import validates

from app import db


class AccountOwner(enum.Enum):
    CLIENT_1 = "client_1"
    CLIENT_2 = "client_2"
    JOINT = "joint"


class AccountCategory(enum.Enum):
    RETIREMENT = "retirement"
    NON_RETIREMENT = "non_retirement"
    TRUST = "trust"


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner = db.Column(
        db.Enum(AccountOwner, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    category = db.Column(
        db.Enum(AccountCategory, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    type = db.Column(db.String(60), nullable=False)
    account_number_last_4 = db.Column(db.String(8), nullable=True)
    label = db.Column(db.String(160), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    balances = db.relationship(
        "AccountBalance",
        backref="account",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AccountBalance.as_of_date.desc()",
    )

    @property
    def latest_balance(self):
        return self.balances[0] if self.balances else None


class AccountBalance(db.Model):
    __tablename__ = "account_balances"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(
        db.Integer,
        db.ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("quarterly_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    balance = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    cash_balance = db.Column(db.Numeric(14, 2), nullable=True)
    as_of_date = db.Column(db.Date, nullable=False)
    is_outdated = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @validates("balance", "cash_balance")
    def _validate_non_negative(self, key, value):
        if value is not None and float(value) < 0:
            raise ValueError(f"{key} must be >= 0")
        return value
