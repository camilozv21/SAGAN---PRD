"""Create all tables and seed a Sample Client based on tcc-sample.png.

Invoke via `flask db-init` or `python -m migrations.init_db`.
"""
from datetime import date
from decimal import Decimal

from app import db
from app.models import (
    Account,
    AccountBalance,
    AccountCategory,
    AccountOwner,
    Client,
    InsurancePolicy,
    Liability,
    Person,
    PersonRole,
    StaticFinancials,
    User,
)


SAMPLE_ADMIN_EMAIL = "admin@example.com"
SAMPLE_ADMIN_PASSWORD = "changeme"


def _d(value):
    return Decimal(str(value))


def _seed_sample_client():
    """Sample Client based on docs/references/tcc-sample.png."""

    existing = Client.query.filter_by(property_address="Sample Family Trust - 123 Placeholder Ln").first()
    if existing:
        return existing

    client = Client(
        property_address="Sample Family Trust - 123 Placeholder Ln",
        transfer_day_of_month=28,
        notes="Sample client seeded from tcc-sample.png.",
    )
    db.session.add(client)

    # --- People ---------------------------------------------------------
    client.people.append(
        Person(
            role=PersonRole.CLIENT_1,
            name="Sample Client 1",
            dob=date(1965, 5, 12),
            ssn_last_4="1234",
            monthly_salary=_d("8000.00"),
        )
    )
    client.people.append(
        Person(
            role=PersonRole.CLIENT_2,
            name="Sample Client 2",
            dob=date(1967, 9, 30),
            ssn_last_4="5678",
            monthly_salary=_d("7000.00"),
        )
    )

    # --- Static financials ---------------------------------------------
    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=_d("12000.00"),
        private_reserve_target_override=None,
    )

    # --- Insurance policies --------------------------------------------
    client.insurance_policies.extend(
        [
            InsurancePolicy(type="Home", deductible=_d("2500.00")),
            InsurancePolicy(type="Auto", deductible=_d("1000.00")),
            InsurancePolicy(type="Health", deductible=_d("3000.00")),
        ]
    )

    # --- Liabilities (from the TCC) ------------------------------------
    liabilities_spec = [
        ("P Mortg", _d("224218.24")),
        ("S Mortg", _d("107587.31")),
        ("Mercedes", _d("11152.00")),
        ("GMC Sierra", _d("25992.00")),
        ("Escalade", _d("31627.52")),
        ("PNC", _d("14026.00")),
        ("Health", _d("1447.00")),
    ]
    for name, balance in liabilities_spec:
        client.liabilities.append(
            Liability(name=name, balance=balance, as_of_date=date(2023, 7, 25))
        )

    # --- Accounts + balances -------------------------------------------
    as_of = date(2023, 7, 25)

    def _acct(owner, category, type_, label, balance, cash=None, outdated=False, last4=None):
        acct = Account(
            owner=owner,
            category=category,
            type=type_,
            label=label,
            account_number_last_4=last4,
            is_active=True,
        )
        acct.balances.append(
            AccountBalance(
                balance=balance,
                cash_balance=cash,
                as_of_date=as_of,
                is_outdated=outdated,
            )
        )
        client.accounts.append(acct)
        return acct

    # Retirement - Client 1
    _acct(AccountOwner.CLIENT_1, AccountCategory.RETIREMENT, "Roth IRA", "Roth IRA", _d("11162.47"), cash=_d("316.00"))
    _acct(AccountOwner.CLIENT_1, AccountCategory.RETIREMENT, "IRA", "IRA", _d("0.00"))

    # Retirement - Client 2
    _acct(AccountOwner.CLIENT_2, AccountCategory.RETIREMENT, "IRA", "IRA", _d("37232.46"), cash=_d("914.00"))
    _acct(AccountOwner.CLIENT_2, AccountCategory.RETIREMENT, "401K", "401K", _d("70042.00"), outdated=True)
    _acct(AccountOwner.CLIENT_2, AccountCategory.RETIREMENT, "Roth IRA", "Roth IRA", _d("18885.92"), cash=_d("508.00"))

    # Non-retirement - Client 1
    _acct(AccountOwner.CLIENT_1, AccountCategory.NON_RETIREMENT, "Checking", "Wells Fargo Main Checking", _d("448.26"))
    _acct(AccountOwner.CLIENT_1, AccountCategory.NON_RETIREMENT, "Savings", "Wells Fargo Savings", _d("44024.00"))
    _acct(AccountOwner.CLIENT_1, AccountCategory.NON_RETIREMENT, "FICA", "StoneCastle FICA", _d("44067.78"))
    _acct(AccountOwner.CLIENT_1, AccountCategory.NON_RETIREMENT, "Brokerage", "Schwab JT TEN", _d("0.00"))

    # Non-retirement - Client 2 (Pinnacle cashflow accounts)
    _acct(AccountOwner.CLIENT_2, AccountCategory.NON_RETIREMENT, "Checking", "Pinnacle Inflow", _d("990.00"))
    _acct(AccountOwner.CLIENT_2, AccountCategory.NON_RETIREMENT, "Checking", "Pinnacle Outflow", _d("12990.00"))
    _acct(AccountOwner.CLIENT_2, AccountCategory.NON_RETIREMENT, "Savings", "Pinnacle Private Reserve", _d("86788.00"))

    # Trust
    _acct(
        AccountOwner.JOINT,
        AccountCategory.TRUST,
        "Trust",
        "Client 1 and Client 2 Family Trust",
        _d("0.00"),
    )

    db.session.flush()
    return client


def _seed_admin_user():
    existing = User.query.filter_by(email=SAMPLE_ADMIN_EMAIL).first()
    if existing:
        return existing
    user = User(email=SAMPLE_ADMIN_EMAIL, name="Admin", is_admin=True)
    user.set_password(SAMPLE_ADMIN_PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def init_database():
    """Create tables (idempotent) and seed sample data."""
    db.create_all()
    # Apply incremental migrations for columns added after initial schema.
    # Must run before any queries so existing databases get new columns
    # before SQLAlchemy tries to SELECT them.
    from migrations.phase6_add_columns import migrate as phase6_migrate
    phase6_migrate()
    client = _seed_sample_client()
    user = _seed_admin_user()
    db.session.commit()
    return {
        "sample_client_id": client.id,
        "admin_user_id": user.id,
        "admin_email": SAMPLE_ADMIN_EMAIL,
    }


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        summary = init_database()
        print("Database initialized:", summary)
