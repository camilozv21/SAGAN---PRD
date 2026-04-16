"""End-to-end tests for the `clients` blueprint CRUD flows."""
from decimal import Decimal

from app.models import (
    Account,
    AccountCategory,
    Client,
    InsurancePolicy,
    Liability,
    Person,
    PersonRole,
)


# --- Helpers ----------------------------------------------------------------
def _married_payload(**overrides):
    """Minimal valid payload for creating a married client with every section."""
    payload = {
        "is_married": "on",
        "has_trust": "on",
        "property_address": "Smith Family Trust - 1 Main St",
        "transfer_day_of_month": "28",
        "notes": "Created via test.",
        "c1_name": "Alice Smith",
        "c1_dob": "1970-01-01",
        "c1_ssn_last_4": "1234",
        "c1_monthly_salary": "8000.00",
        "c2_name": "Bob Smith",
        "c2_dob": "1972-05-15",
        "c2_ssn_last_4": "5678",
        "c2_monthly_salary": "5000.00",
        # Retirement: C1 Roth IRA + C2 401K
        "retirement_owner[]": ["client_1", "client_2"],
        "retirement_type[]": ["Roth IRA", "401K"],
        "retirement_last4[]": ["1111", "2222"],
        "retirement_label[]": ["Roth IRA", "Corp 401K"],
        # Non-retirement: Joint checking + C1 brokerage
        "nonret_owner[]": ["joint", "client_1"],
        "nonret_type[]": ["Checking", "Brokerage"],
        "nonret_last4[]": ["9999", "8888"],
        "nonret_label[]": ["Wells Fargo Checking", "Schwab JT TEN"],
        # Liabilities
        "liability_name[]": ["P Mortg", "Mercedes"],
        "liability_rate[]": ["0.0650", "0.0499"],
        "liability_balance[]": ["224218.24", "11152.00"],
        # Insurance
        "insurance_type[]": ["Home", "Auto"],
        "insurance_deductible[]": ["2500.00", "1000.00"],
        # Static financials
        "agreed_monthly_outflow": "12000.00",
        "private_reserve_target_override": "",
    }
    payload.update(overrides)
    return payload


def _single_payload(**overrides):
    payload = {
        "property_address": "",
        "transfer_day_of_month": "15",
        "notes": "",
        "c1_name": "Solo Person",
        "c1_dob": "",
        "c1_ssn_last_4": "",
        "c1_monthly_salary": "6500",
        "agreed_monthly_outflow": "4000",
    }
    payload.update(overrides)
    return payload


def _only_client():
    """Return the single Client created in the DB (simplifies assertions)."""
    clients = Client.query.all()
    assert len(clients) == 1, f"expected 1 client, got {len(clients)}"
    return clients[0]


# --- Basic routes -----------------------------------------------------------
def test_list_empty(http):
    resp = http.get("/clients/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "No clients yet" in body or "Clients" in body


def test_root_redirects_to_clients(http):
    resp = http.get("/")
    assert resp.status_code in (301, 302)
    assert "/clients" in resp.headers["Location"]


def test_new_form_renders(http):
    resp = http.get("/clients/new")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "New client" in body
    assert "c1_name" in body


# --- Create married end-to-end ---------------------------------------------
def test_create_married_client_persists_full_shape(http):
    resp = http.post("/clients/", data=_married_payload(), follow_redirects=False)
    assert resp.status_code == 302

    client = _only_client()
    assert client.is_married is True
    assert client.transfer_day_of_month == 28
    assert client.property_address.startswith("Smith Family Trust")

    # People
    c1 = client.person(PersonRole.CLIENT_1)
    c2 = client.person(PersonRole.CLIENT_2)
    assert c1.name == "Alice Smith"
    assert c1.ssn_last_4 == "1234"
    assert c1.monthly_salary == Decimal("8000.00")
    assert c2.name == "Bob Smith"
    assert c2.monthly_salary == Decimal("5000.00")

    # Accounts: 2 retirement + 2 non-retirement + 1 trust = 5
    assert len(client.accounts) == 5
    retirement = [a for a in client.accounts if a.category == AccountCategory.RETIREMENT]
    nonret = [a for a in client.accounts if a.category == AccountCategory.NON_RETIREMENT]
    trust = [a for a in client.accounts if a.category == AccountCategory.TRUST]
    assert len(retirement) == 2
    assert len(nonret) == 2
    assert len(trust) == 1
    assert trust[0].label == "Smith Family Trust - 1 Main St"

    # Liabilities
    assert len(client.liabilities) == 2
    liabs_by_name = {l.name: l for l in client.liabilities}
    assert liabs_by_name["P Mortg"].balance == Decimal("224218.24")
    assert liabs_by_name["P Mortg"].interest_rate == Decimal("0.0650")

    # Insurance
    assert len(client.insurance_policies) == 2
    assert client.insurance_policies[0].type in ("Home", "Auto")

    # Static financials
    sf = client.static_financials
    assert sf is not None
    assert sf.agreed_monthly_outflow == Decimal("12000.00")
    assert sf.private_reserve_target_override is None


# --- Create single ---------------------------------------------------------
def test_create_single_client(http):
    resp = http.post("/clients/", data=_single_payload(), follow_redirects=False)
    assert resp.status_code == 302

    client = _only_client()
    assert client.is_married is False
    assert client.person(PersonRole.CLIENT_2) is None
    assert len(client.accounts) == 0
    assert client.static_financials.agreed_monthly_outflow == Decimal("4000")


# --- Detail view -----------------------------------------------------------
def test_detail_view_renders(http):
    http.post("/clients/", data=_married_payload(), follow_redirects=False)
    client = _only_client()

    resp = http.get(f"/clients/{client.id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Alice Smith" in body
    assert "Bob Smith" in body
    assert "P Mortg" in body
    assert "Smith Family Trust" in body


def test_detail_view_404_for_missing(http):
    resp = http.get("/clients/999")
    assert resp.status_code == 404


# --- Edit ------------------------------------------------------------------
def test_edit_updates_basic_fields_and_recreates_children(http):
    http.post("/clients/", data=_married_payload(), follow_redirects=False)
    client = _only_client()
    client_id = client.id

    # Edit: change C1 salary, keep 1 retirement + 0 non-retirement, drop trust.
    updated = _married_payload(**{
        "c1_monthly_salary": "9500.00",
        "has_trust": "",  # disable trust
        "transfer_day_of_month": "1",
        "retirement_owner[]": ["client_1"],
        "retirement_type[]": ["IRA"],
        "retirement_last4[]": ["0001"],
        "retirement_label[]": ["Post-edit IRA"],
        "nonret_owner[]": [],
        "nonret_type[]": [],
        "nonret_last4[]": [],
        "nonret_label[]": [],
        "liability_name[]": [],
        "liability_rate[]": [],
        "liability_balance[]": [],
        "insurance_type[]": [],
        "insurance_deductible[]": [],
    })
    resp = http.post(f"/clients/{client_id}", data=updated, follow_redirects=False)
    assert resp.status_code == 302

    refetched = Client.query.get(client_id)
    assert refetched.person(PersonRole.CLIENT_1).monthly_salary == Decimal("9500.00")
    assert refetched.transfer_day_of_month == 1
    retirement = [a for a in refetched.accounts if a.category == AccountCategory.RETIREMENT]
    trust = [a for a in refetched.accounts if a.category == AccountCategory.TRUST]
    assert len(retirement) == 1
    assert retirement[0].label == "Post-edit IRA"
    assert len(trust) == 0
    assert len(refetched.liabilities) == 0
    assert len(refetched.insurance_policies) == 0


def test_edit_toggle_married_to_single_drops_c2(http):
    http.post("/clients/", data=_married_payload(), follow_redirects=False)
    client = _only_client()
    client_id = client.id

    payload = _married_payload()
    payload.pop("is_married")
    # Once single, the household cannot have Client 2 accounts.
    payload["retirement_owner[]"] = ["client_1"]
    payload["retirement_type[]"] = ["Roth IRA"]
    payload["retirement_last4[]"] = ["1111"]
    payload["retirement_label[]"] = ["Roth IRA"]
    payload["nonret_owner[]"] = ["client_1"]
    payload["nonret_type[]"] = ["Checking"]
    payload["nonret_last4[]"] = ["0000"]
    payload["nonret_label[]"] = ["WF"]

    resp = http.post(f"/clients/{client_id}", data=payload, follow_redirects=False)
    assert resp.status_code == 302

    refetched = Client.query.get(client_id)
    assert refetched.is_married is False
    assert refetched.person(PersonRole.CLIENT_2) is None


# --- Delete ---------------------------------------------------------------
def test_delete_removes_client_and_children(http):
    http.post("/clients/", data=_married_payload(), follow_redirects=False)
    client = _only_client()
    client_id = client.id

    resp = http.post(f"/clients/{client_id}/delete", follow_redirects=False)
    assert resp.status_code == 302

    assert Client.query.get(client_id) is None
    assert Person.query.filter_by(client_id=client_id).count() == 0
    assert Account.query.filter_by(client_id=client_id).count() == 0
    assert Liability.query.filter_by(client_id=client_id).count() == 0
    assert InsurancePolicy.query.filter_by(client_id=client_id).count() == 0


# --- Validation failures --------------------------------------------------
def test_create_requires_c1_name(http):
    payload = _married_payload(c1_name="")
    resp = http.post("/clients/", data=payload, follow_redirects=False)
    assert resp.status_code == 400
    assert Client.query.count() == 0


def test_create_rejects_bad_ssn(http):
    payload = _married_payload(c1_ssn_last_4="12a4")
    resp = http.post("/clients/", data=payload, follow_redirects=False)
    assert resp.status_code == 400
    assert Client.query.count() == 0


def test_create_rejects_transfer_day_out_of_range(http):
    payload = _married_payload(transfer_day_of_month="32")
    resp = http.post("/clients/", data=payload, follow_redirects=False)
    assert resp.status_code == 400
    assert Client.query.count() == 0


def test_create_rejects_negative_salary(http):
    payload = _married_payload(c1_monthly_salary="-100")
    resp = http.post("/clients/", data=payload, follow_redirects=False)
    assert resp.status_code == 400
    assert Client.query.count() == 0


def test_single_client_cannot_have_c2_account(http):
    payload = _single_payload(**{
        "retirement_owner[]": ["client_2"],
        "retirement_type[]": ["IRA"],
        "retirement_last4[]": ["0000"],
        "retirement_label[]": [""],
    })
    resp = http.post("/clients/", data=payload, follow_redirects=False)
    assert resp.status_code == 400
    assert Client.query.count() == 0


def test_create_rejects_invalid_account_type(http):
    payload = _married_payload(**{
        "retirement_owner[]": ["client_1"],
        "retirement_type[]": ["NotAType"],
        "retirement_last4[]": [""],
        "retirement_label[]": [""],
    })
    resp = http.post("/clients/", data=payload, follow_redirects=False)
    assert resp.status_code == 400
    assert Client.query.count() == 0
