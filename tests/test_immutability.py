"""Immutability tests (Phase 7).

Verify that editing a client after report creation does NOT alter old reports.
"""
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
    QuarterlyReport,
    StaticFinancials,
)


def _seed_client_with_report(session):
    """Create a client, generate a report snapshot, return (client, report)."""
    client = Client(transfer_day_of_month=28, property_address="Immutable Trust")
    client.people.append(Person(
        role=PersonRole.CLIENT_1, name="Freeze C1",
        monthly_salary=Decimal("8000"),
    ))
    client.people.append(Person(
        role=PersonRole.CLIENT_2, name="Freeze C2",
        monthly_salary=Decimal("7000"),
    ))
    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=Decimal("10000"),
    )
    client.insurance_policies.append(
        InsurancePolicy(type="Home", deductible=Decimal("2500")),
    )

    ira = Account(
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.RETIREMENT,
        type="IRA", label="C1 IRA",
    )
    fica = Account(
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT,
        type="FICA", label="FICA Account",
    )
    client.accounts.extend([ira, fica])
    client.liabilities.append(
        Liability(name="Mortgage", balance=Decimal("200000")),
    )

    session.add(client)
    session.flush()

    from datetime import date
    report = QuarterlyReport(
        client_id=client.id,
        report_date=date(2025, 3, 31),
        inflow_client_1_snapshot=Decimal("8000"),
        inflow_client_2_snapshot=Decimal("7000"),
        outflow_snapshot=Decimal("10000"),
        trust_value_snapshot=Decimal("0"),
        target_snapshot=Decimal("62500"),
        transfer_day_snapshot=28,
    )
    report.set_liabilities_snapshot([
        {"name": "Mortgage", "balance": "200000", "as_of_date": None},
    ])
    session.add(report)
    session.flush()

    session.add(AccountBalance(
        account_id=ira.id, report_id=report.id,
        balance=Decimal("100000"), as_of_date=date(2025, 3, 31),
    ))
    session.add(AccountBalance(
        account_id=fica.id, report_id=report.id,
        balance=Decimal("75000"), as_of_date=date(2025, 3, 31),
    ))
    session.commit()

    return client, report


def test_editing_client_salary_does_not_change_report(app, session):
    client, report = _seed_client_with_report(session)
    report_id = report.id

    # Edit the client's salary
    c1 = client.person(PersonRole.CLIENT_1)
    c1.monthly_salary = Decimal("15000")
    session.commit()

    # Report snapshot should be untouched
    r = QuarterlyReport.query.get(report_id)
    assert float(r.inflow_client_1_snapshot) == 8000.0
    assert float(r.inflow_client_2_snapshot) == 7000.0


def test_editing_client_outflow_does_not_change_report(app, session):
    client, report = _seed_client_with_report(session)
    report_id = report.id

    client.static_financials.agreed_monthly_outflow = Decimal("20000")
    session.commit()

    r = QuarterlyReport.query.get(report_id)
    assert float(r.outflow_snapshot) == 10000.0


def test_adding_account_does_not_change_report_balances(app, session):
    client, report = _seed_client_with_report(session)
    report_id = report.id

    # Add a new account to the client
    new_acct = Account(
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.RETIREMENT,
        type="401K", label="New 401K",
    )
    client.accounts.append(new_acct)
    session.commit()

    # Old report should still have only 2 balances
    balances = AccountBalance.query.filter_by(report_id=report_id).all()
    assert len(balances) == 2
    assert all(float(b.balance) in (100000.0, 75000.0) for b in balances)


def test_liability_snapshot_survives_live_edit(app, session):
    client, report = _seed_client_with_report(session)
    report_id = report.id

    # Edit the live liability
    client.liabilities[0].balance = Decimal("150000")
    session.commit()

    # Report snapshot should show original value
    r = QuarterlyReport.query.get(report_id)
    snap = r.get_liabilities_snapshot()
    assert snap is not None
    assert float(snap[0]["balance"]) == 200000.0


def test_transfer_day_snapshot_survives_edit(app, session):
    client, report = _seed_client_with_report(session)
    report_id = report.id

    client.transfer_day_of_month = 1
    session.commit()

    r = QuarterlyReport.query.get(report_id)
    assert r.transfer_day_snapshot == 28
