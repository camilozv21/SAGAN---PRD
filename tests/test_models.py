from datetime import date
from decimal import Decimal

import pytest

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


def _build_base_client(session, *, married=True):
    client = Client(
        property_address="Test Trust — 9 Fake Ln",
        transfer_day_of_month=28,
        notes="fixture",
    )
    client.people.append(
        Person(
            role=PersonRole.CLIENT_1,
            name="C1 Test",
            dob=date(1970, 1, 1),
            ssn_last_4="1234",
            monthly_salary=Decimal("8000.00"),
        )
    )
    if married:
        client.people.append(
            Person(
                role=PersonRole.CLIENT_2,
                name="C2 Test",
                dob=date(1972, 2, 2),
                ssn_last_4="5678",
                monthly_salary=Decimal("5000.00"),
            )
        )
    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=Decimal("10000.00")
    )
    session.add(client)
    session.flush()
    return client


def test_create_married_client_full(session):
    client = _build_base_client(session, married=True)

    acct = Account(
        client_id=client.id,
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.RETIREMENT,
        type="Roth IRA",
        label="Roth IRA",
    )
    acct.balances.append(
        AccountBalance(
            balance=Decimal("11162.47"),
            cash_balance=Decimal("316.00"),
            as_of_date=date(2023, 7, 25),
        )
    )
    client.accounts.append(acct)
    client.liabilities.append(
        Liability(name="P Mortg", balance=Decimal("224218.24"), as_of_date=date(2023, 7, 25))
    )
    client.insurance_policies.append(
        InsurancePolicy(type="Home", deductible=Decimal("2500.00"))
    )
    session.commit()

    refetched = Client.query.get(client.id)
    assert refetched.is_married is True
    assert len(refetched.people) == 2
    assert {p.role for p in refetched.people} == {PersonRole.CLIENT_1, PersonRole.CLIENT_2}
    assert refetched.person(PersonRole.CLIENT_1).name == "C1 Test"
    assert len(refetched.accounts) == 1
    assert refetched.accounts[0].latest_balance.balance == Decimal("11162.47")
    assert refetched.accounts[0].latest_balance.cash_balance == Decimal("316.00")
    assert len(refetched.liabilities) == 1
    assert len(refetched.insurance_policies) == 1
    assert refetched.static_financials.agreed_monthly_outflow == Decimal("10000.00")


def test_create_single_client(session):
    client = _build_base_client(session, married=False)
    session.commit()

    refetched = Client.query.get(client.id)
    assert refetched.is_married is False
    assert len(refetched.people) == 1
    assert refetched.people[0].role == PersonRole.CLIENT_1
    assert refetched.person(PersonRole.CLIENT_2) is None


def test_cascade_delete_removes_children(session):
    client = _build_base_client(session, married=True)
    acct = Account(
        client_id=client.id,
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT,
        type="Checking",
        label="WF Checking",
    )
    acct.balances.append(
        AccountBalance(balance=Decimal("500.00"), as_of_date=date(2023, 7, 25))
    )
    client.accounts.append(acct)
    client.liabilities.append(
        Liability(name="Auto", balance=Decimal("10000.00"))
    )
    client.insurance_policies.append(
        InsurancePolicy(type="Home", deductible=Decimal("1500.00"))
    )
    session.commit()

    client_id = client.id
    session.delete(client)
    session.commit()

    assert Client.query.get(client_id) is None
    assert Person.query.filter_by(client_id=client_id).count() == 0
    assert Account.query.filter_by(client_id=client_id).count() == 0
    assert AccountBalance.query.count() == 0
    assert Liability.query.filter_by(client_id=client_id).count() == 0
    assert InsurancePolicy.query.filter_by(client_id=client_id).count() == 0
    assert StaticFinancials.query.filter_by(client_id=client_id).count() == 0


@pytest.mark.parametrize("bad_value", ["123", "12345", "12a4", "abcd", " 123"])
def test_ssn_last_4_rejects_invalid(bad_value):
    with pytest.raises(ValueError):
        Person(
            role=PersonRole.CLIENT_1,
            name="x",
            monthly_salary=Decimal("0"),
            ssn_last_4=bad_value,
        )


def test_ssn_last_4_accepts_none_and_valid():
    Person(role=PersonRole.CLIENT_1, name="x", ssn_last_4=None)
    Person(role=PersonRole.CLIENT_1, name="x", ssn_last_4="0000")
    Person(role=PersonRole.CLIENT_1, name="x", ssn_last_4="9999")


def test_negative_balance_rejected():
    with pytest.raises(ValueError):
        AccountBalance(balance=Decimal("-1"), as_of_date=date(2023, 1, 1))
    with pytest.raises(ValueError):
        AccountBalance(
            balance=Decimal("0"),
            cash_balance=Decimal("-0.01"),
            as_of_date=date(2023, 1, 1),
        )


def test_transfer_day_out_of_range_rejected():
    with pytest.raises(ValueError):
        Client(transfer_day_of_month=0)
    with pytest.raises(ValueError):
        Client(transfer_day_of_month=32)


def test_user_password_roundtrip(session):
    user = User(email="Someone@Example.COM", name="S")
    user.set_password("hunter2")
    session.add(user)
    session.commit()

    fetched = User.query.filter_by(email="someone@example.com").first()
    assert fetched is not None
    assert fetched.email == "someone@example.com"
    assert fetched.check_password("hunter2") is True
    assert fetched.check_password("nope") is False


def test_duplicate_person_role_rejected(session):
    client = Client(transfer_day_of_month=15)
    client.people.append(Person(role=PersonRole.CLIENT_1, name="A"))
    client.people.append(Person(role=PersonRole.CLIENT_1, name="B"))
    session.add(client)
    with pytest.raises(Exception):
        session.commit()
    session.rollback()
