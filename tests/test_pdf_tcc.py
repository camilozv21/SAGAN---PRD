"""TCC PDF generation (Phase 5)."""
from datetime import date
from decimal import Decimal

import pytest

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
from app.services.pdf_generator import (
    build_tcc_context,
    group_tcc_accounts,
    tcc_filename,
)

try:
    from weasyprint import HTML as _HTML  # noqa: F401

    WEASYPRINT_OK = True
    WEASYPRINT_SKIP_REASON = ""
except Exception as exc:  # pragma: no cover - environment-dependent
    WEASYPRINT_OK = False
    WEASYPRINT_SKIP_REASON = f"WeasyPrint native libs unavailable: {exc!s}"


# --- Fixtures --------------------------------------------------------------
def _add_account(client, *, owner, category, type_, label=None, last4=None):
    acct = Account(
        owner=owner,
        category=category,
        type=type_,
        label=label,
        account_number_last_4=last4,
    )
    client.accounts.append(acct)
    return acct


def _add_balance(session, *, account, report, balance, as_of,
                 cash_balance=None, is_outdated=False):
    session.add(AccountBalance(
        account_id=account.id,
        report_id=report.id,
        balance=Decimal(str(balance)),
        cash_balance=(
            Decimal(str(cash_balance)) if cash_balance is not None else None
        ),
        as_of_date=as_of,
        is_outdated=is_outdated,
    ))


def _seed_sample_report(session):
    """Replicate the Sample Client screenshot: 5 retirement accounts,
    4 non-retirement, 1 trust, 7 liabilities, married household."""
    client = Client(transfer_day_of_month=28, property_address="123 Main St")
    client.people.append(Person(
        role=PersonRole.CLIENT_1, name="Sample Client 1",
        dob=date(1960, 5, 10), ssn_last_4="1234",
        monthly_salary=Decimal("8000"),
    ))
    client.people.append(Person(
        role=PersonRole.CLIENT_2, name="Sample Client 2",
        dob=date(1962, 7, 22), ssn_last_4="5678",
        monthly_salary=Decimal("7000"),
    ))
    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=Decimal("12000"),
    )
    client.insurance_policies.append(
        InsurancePolicy(type="Home", deductible=Decimal("2500"))
    )

    # Retirement accounts
    c1_roth = _add_account(
        client, owner=AccountOwner.CLIENT_1,
        category=AccountCategory.RETIREMENT, type_="Roth IRA",
        last4="1111",
    )
    c2_ira = _add_account(
        client, owner=AccountOwner.CLIENT_2,
        category=AccountCategory.RETIREMENT, type_="IRA", last4="2222",
    )
    c2_401k = _add_account(
        client, owner=AccountOwner.CLIENT_2,
        category=AccountCategory.RETIREMENT, type_="401K", last4="3333",
    )
    c2_roth = _add_account(
        client, owner=AccountOwner.CLIENT_2,
        category=AccountCategory.RETIREMENT, type_="Roth IRA", last4="4444",
    )

    # Non-retirement
    c1_checking = _add_account(
        client, owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT, type_="Checking",
        label="Wells Fargo Main Checking", last4="5555",
    )
    c1_fica = _add_account(
        client, owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT, type_="FICA",
        label="StoneCastle FICA", last4="6666",
    )
    c1_savings = _add_account(
        client, owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT, type_="Savings",
        label="Wells Fargo Savings", last4="7777",
    )
    joint_brokerage = _add_account(
        client, owner=AccountOwner.JOINT,
        category=AccountCategory.NON_RETIREMENT, type_="Brokerage",
        label="Schwab JT TEN", last4="8888",
    )

    # Trust
    trust_acct = _add_account(
        client, owner=AccountOwner.JOINT,
        category=AccountCategory.TRUST, type_="Family Trust", last4="9999",
    )

    # Liabilities — the 7 from the screenshot
    for name, bal in [
        ("P Mortg", "224218.24"),
        ("S Mortg", "107587.31"),
        ("Mercedes", "11152.00"),
        ("Sonata", "15042.52"),
        ("Escalade", "3867.00"),
        ("GMC Yukon", "22500.00"),
        ("PNC", "31693.00"),
    ]:
        client.liabilities.append(
            Liability(name=name, balance=Decimal(bal), as_of_date=date(2023, 7, 25))
        )

    session.add(client)
    session.flush()

    report = QuarterlyReport(
        client_id=client.id,
        report_date=date(2023, 7, 26),
        inflow_client_1_snapshot=Decimal("8000"),
        inflow_client_2_snapshot=Decimal("7000"),
        outflow_snapshot=Decimal("12000"),
        trust_value_snapshot=Decimal("0"),
        target_snapshot=Decimal("0"),
    )
    session.add(report)
    session.flush()

    _add_balance(session, account=c1_roth, report=report,
                 balance="11162.47", as_of=date(2023, 7, 25),
                 cash_balance="318")
    _add_balance(session, account=c2_ira, report=report,
                 balance="37232.46", as_of=date(2023, 7, 25),
                 cash_balance="814")
    _add_balance(session, account=c2_401k, report=report,
                 balance="70042.00", as_of=date(2023, 7, 25))
    _add_balance(session, account=c2_roth, report=report,
                 balance="19885.92", as_of=date(2023, 7, 25),
                 cash_balance="508")
    _add_balance(session, account=c1_checking, report=report,
                 balance="948.00", as_of=date(2023, 5, 23),
                 is_outdated=True)
    _add_balance(session, account=c1_fica, report=report,
                 balance="0", as_of=date(2023, 7, 25))
    _add_balance(session, account=c1_savings, report=report,
                 balance="44024.00", as_of=date(2023, 5, 23),
                 is_outdated=True)
    _add_balance(session, account=joint_brokerage, report=report,
                 balance="0", as_of=date(2023, 7, 25))
    _add_balance(session, account=trust_acct, report=report,
                 balance="0", as_of=date(2023, 7, 25))

    session.commit()
    return client, report


def _seed_single_client(session):
    """Unmarried client — only Client 1, no Client 2."""
    client = Client(transfer_day_of_month=15, property_address="Solo Ln")
    client.people.append(Person(
        role=PersonRole.CLIENT_1, name="Solo Person",
        dob=date(1975, 1, 15), ssn_last_4="0000",
        monthly_salary=Decimal("5000"),
    ))
    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=Decimal("4000"),
    )
    ira = _add_account(
        client, owner=AccountOwner.CLIENT_1,
        category=AccountCategory.RETIREMENT, type_="IRA", last4="1111",
    )
    checking = _add_account(
        client, owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT, type_="Checking",
        label="Solo Checking", last4="2222",
    )

    session.add(client)
    session.flush()

    report = QuarterlyReport(
        client_id=client.id,
        report_date=date(2026, 1, 15),
        inflow_client_1_snapshot=Decimal("5000"),
        inflow_client_2_snapshot=Decimal("0"),
        outflow_snapshot=Decimal("4000"),
        trust_value_snapshot=Decimal("0"),
        target_snapshot=Decimal("0"),
    )
    session.add(report)
    session.flush()

    _add_balance(session, account=ira, report=report,
                 balance="50000", as_of=date(2026, 1, 15))
    _add_balance(session, account=checking, report=report,
                 balance="8000", as_of=date(2026, 1, 15))
    session.commit()

    return client, report


# --- Grouping + context ----------------------------------------------------
def test_group_tcc_accounts_distributes_by_owner(session):
    _, report = _seed_sample_report(session)
    grouped = group_tcc_accounts(report)

    # Retirement: 1 C1, 3 C2
    assert len(grouped["retirement_c1"]) == 1
    assert len(grouped["retirement_c2"]) == 3
    assert grouped["retirement_c1"][0]["type"] == "Roth IRA"

    # Non-retirement: 3 owned by C1 + 1 joint → balancer pushes joint to C2.
    assert len(grouped["non_retirement_c1"]) == 3
    assert len(grouped["non_retirement_c2"]) == 1
    # Joint should have landed in C2 side.
    c2_labels = [e["label"] for e in grouped["non_retirement_c2"]]
    assert "Schwab JT TEN" in c2_labels

    # Trust + liabilities
    assert len(grouped["trust_accounts"]) == 1
    assert len(grouped["liabilities"]) == 7


def test_build_tcc_context_totals(session):
    _, report = _seed_sample_report(session)
    ctx = build_tcc_context(report)

    # C1 retirement = 11162.47
    assert ctx["c1_retirement_total"] == Decimal("11162.47")
    # C2 retirement = 37232.46 + 70042 + 19885.92 = 127160.38
    assert ctx["c2_retirement_total"] == Decimal("127160.38")
    # Non-retirement = 948 + 0 + 44024 + 0 = 44972 (trust excluded)
    assert ctx["non_retirement_total"] == Decimal("44972.00")
    # Grand total = c1 + c2 + non-retirement + trust(0)
    assert ctx["grand_total"] == Decimal("183294.85")
    # Liabilities total
    assert ctx["liabilities_total"] == Decimal("416060.07")
    # Outdated flag picked up from C1 checking + savings
    assert ctx["any_outdated"] is True


def test_build_tcc_context_single_client(session):
    _, report = _seed_single_client(session)
    ctx = build_tcc_context(report)
    assert ctx["c1"] is not None
    assert ctx["c2"] is None
    assert ctx["c1_retirement_total"] == Decimal("50000")
    assert ctx["c2_retirement_total"] == Decimal("0")
    assert ctx["non_retirement_total"] == Decimal("8000")
    assert ctx["any_outdated"] is False


def test_tcc_filename_is_safe(session):
    _, report = _seed_sample_report(session)
    name = tcc_filename(report)
    assert name.startswith("TCC_")
    assert name.endswith(".pdf")
    assert "2023-07-26" in name
    assert " " not in name


# --- Template rendering (pure Jinja, no WeasyPrint) -----------------------
def test_tcc_template_renders_every_section(session):
    from app.services.pdf_generator import _env

    _, report = _seed_sample_report(session)
    ctx = build_tcc_context(report)
    html = _env.get_template("tcc.html").render(**ctx)

    # Header
    assert "NAME:" in html and "DATE:" in html
    assert "July 26, 2023" in html
    assert "GRAND TOTAL" in html

    # Client circles
    assert "Sample Client 1" in html
    assert "Sample Client 2" in html

    # Section labels
    assert "RETIREMENT" in html
    assert "NON RETIREMENT" in html

    # Account bubbles — balance + date + outdated asterisk
    assert "$11,162.47" in html
    assert "$37,232.46" in html
    assert "$44,024.00" in html
    assert "07/25/2023" in html
    assert 'class="ast"' in html  # outdated accounts render asterisk

    # Cash sub-bubbles appear for three accounts
    assert "$318 Cash" in html
    assert "$814 Cash" in html
    assert "$508 Cash" in html

    # Trust oval
    assert "Family" in html
    assert "Trust" in html

    # Liabilities
    assert "P Mortg" in html
    assert "Mercedes" in html
    assert "$416,060.07" in html
    assert "NON RETIREMENT TOTAL" in html

    # Outdated footer note
    assert "* Indicates we do not have up to date information" in html


def test_tcc_template_handles_single_client(session):
    from app.services.pdf_generator import _env

    _, report = _seed_single_client(session)
    ctx = build_tcc_context(report)
    html = _env.get_template("tcc.html").render(**ctx)

    assert "Solo Person" in html
    # Client 2 retirement-only box should be hidden, not errored.
    assert "visibility:hidden" in html
    # Outdated footnote should NOT appear.
    assert "* Indicates" not in html


def test_tcc_template_no_liabilities(session, app):
    from app.services.pdf_generator import _env

    _, report = _seed_single_client(session)
    # seed_single_client has no liabilities.
    ctx = build_tcc_context(report)
    html = _env.get_template("tcc.html").render(**ctx)

    assert "No liabilities recorded." in html


def test_tcc_template_outdated_asterisk_only_when_flagged(session):
    from app.services.pdf_generator import _env

    _, report = _seed_single_client(session)
    ctx = build_tcc_context(report)
    html = _env.get_template("tcc.html").render(**ctx)

    # No account was flagged outdated.
    assert 'class="ast"' not in html


def test_tcc_template_cash_bubble_only_when_present(session):
    from app.services.pdf_generator import _env

    _, report = _seed_single_client(session)  # no cash_balance anywhere
    ctx = build_tcc_context(report)
    html = _env.get_template("tcc.html").render(**ctx)
    assert "Cash</div>" not in html


# --- Render-path tests (require WeasyPrint) --------------------------------
@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_generate_tcc_pdf_returns_bytes(session):
    from app.services.pdf_generator import generate_tcc_pdf

    _, report = _seed_sample_report(session)
    pdf_bytes = generate_tcc_pdf(report.id)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000


@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_generate_tcc_pdf_is_single_page(session):
    from io import BytesIO

    import pypdf

    from app.services.pdf_generator import generate_tcc_pdf

    _, report = _seed_sample_report(session)
    pdf_bytes = generate_tcc_pdf(report.id)
    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 1


@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_generate_tcc_pdf_single_client(session):
    from app.services.pdf_generator import generate_tcc_pdf

    _, report = _seed_single_client(session)
    pdf_bytes = generate_tcc_pdf(report.id)
    assert pdf_bytes.startswith(b"%PDF-")


@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_tcc_route_returns_pdf_response(http, session):
    client, report = _seed_sample_report(session)
    resp = http.get(f"/clients/{client.id}/reports/{report.id}/tcc.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF-")
    assert "TCC_" in resp.headers.get("Content-Disposition", "")


def test_tcc_route_404_for_missing_report(http, app):
    resp = http.get("/clients/9999/reports/9999/tcc.pdf")
    assert resp.status_code == 404


@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_both_zip_route_returns_zip(http, session):
    import io
    import zipfile

    client, report = _seed_sample_report(session)
    resp = http.get(f"/clients/{client.id}/reports/{report.id}/both.zip")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        names = zf.namelist()
    assert any(n.startswith("SACS_") for n in names)
    assert any(n.startswith("TCC_") for n in names)
