"""SACS PDF generation (Phase 4)."""
from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.models import (
    AccountBalance,
    AccountCategory,
    AccountOwner,
    Client,
    InsurancePolicy,
    Person,
    PersonRole,
    QuarterlyReport,
    StaticFinancials,
)
from app.services.pdf_generator import (
    build_sacs_context,
    format_currency,
    sacs_filename,
)

# WeasyPrint relies on GTK native libs (pango, cairo, gobject). On Windows
# dev machines without GTK these fail at import time. Skipping the
# render-the-bytes tests lets the suite stay green locally while still
# covering generation on Linux/Railway.
try:
    from weasyprint import HTML as _HTML  # noqa: F401

    WEASYPRINT_OK = True
    WEASYPRINT_SKIP_REASON = ""
except Exception as exc:  # pragma: no cover - environment-dependent
    WEASYPRINT_OK = False
    WEASYPRINT_SKIP_REASON = f"WeasyPrint native libs unavailable: {exc!s}"


# --- Fixtures --------------------------------------------------------------
def _seed_report(session, *, salary_c1=8000, salary_c2=7000, outflow=12000,
                 fica=75000, schwab=15000, transfer_day=28):
    """Build a minimal client with one FICA + one Brokerage + one report."""
    client = Client(transfer_day_of_month=transfer_day,
                    property_address="123 Test St")
    client.people.append(Person(
        role=PersonRole.CLIENT_1, name="Jane Doe",
        monthly_salary=Decimal(str(salary_c1)),
    ))
    client.people.append(Person(
        role=PersonRole.CLIENT_2, name="John Doe",
        monthly_salary=Decimal(str(salary_c2)),
    ))
    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=Decimal(str(outflow)),
    )
    client.insurance_policies.append(
        InsurancePolicy(type="Home", deductible=Decimal("2500"))
    )

    from app.models import Account
    fica_acct = Account(
        owner=AccountOwner.CLIENT_1, category=AccountCategory.NON_RETIREMENT,
        type="FICA", label="StoneCastle FICA",
    )
    brokerage_acct = Account(
        owner=AccountOwner.CLIENT_1, category=AccountCategory.NON_RETIREMENT,
        type="Brokerage", label="Schwab Joint",
    )
    client.accounts.append(fica_acct)
    client.accounts.append(brokerage_acct)

    session.add(client)
    session.flush()

    report = QuarterlyReport(
        client_id=client.id,
        report_date=date(2026, 3, 31),
        inflow_client_1_snapshot=Decimal(str(salary_c1)),
        inflow_client_2_snapshot=Decimal(str(salary_c2)),
        outflow_snapshot=Decimal(str(outflow)),
        trust_value_snapshot=Decimal("0"),
        target_snapshot=Decimal("0"),
    )
    session.add(report)
    session.flush()

    session.add(AccountBalance(
        account_id=fica_acct.id, report_id=report.id,
        balance=Decimal(str(fica)), as_of_date=date(2026, 3, 31),
    ))
    session.add(AccountBalance(
        account_id=brokerage_acct.id, report_id=report.id,
        balance=Decimal(str(schwab)), as_of_date=date(2026, 3, 31),
    ))
    session.commit()

    return client, report


# --- Pure-python tests (no WeasyPrint required) ----------------------------
def test_format_currency_no_decimals():
    assert format_currency(Decimal("1234.56")) == "$1,235"
    assert format_currency(1000) == "$1,000"
    assert format_currency(0) == "$0"
    assert format_currency(None) == "$0"


def test_format_currency_with_decimals():
    assert format_currency(Decimal("1234.5"), decimals=2) == "$1,234.50"


def test_format_currency_negative():
    assert format_currency(Decimal("-500")) == "-$500"


def test_build_context_matches_snapshot(session):
    _, report = _seed_report(session)
    ctx = build_sacs_context(report)

    assert ctx["client_name"] == "Jane Doe & John Doe"
    assert ctx["salary_c1"] == Decimal("8000")
    assert ctx["salary_c2"] == Decimal("7000")
    assert ctx["inflow_total"] == Decimal("15000")
    assert ctx["outflow"] == Decimal("12000")
    assert ctx["excess"] == Decimal("3000")
    assert ctx["transfer_day"] == 28
    assert ctx["private_reserve_balance"] == Decimal("75000")
    assert ctx["schwab_balance"] == Decimal("15000")


def test_build_context_handles_missing_accounts(session):
    client = Client(transfer_day_of_month=15, property_address="x")
    client.people.append(Person(
        role=PersonRole.CLIENT_1, name="Solo",
        monthly_salary=Decimal("5000"),
    ))
    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=Decimal("4000"),
    )
    session.add(client)
    session.flush()

    report = QuarterlyReport(
        client_id=client.id,
        report_date=date(2026, 1, 1),
        inflow_client_1_snapshot=Decimal("5000"),
        inflow_client_2_snapshot=Decimal("0"),
        outflow_snapshot=Decimal("4000"),
        trust_value_snapshot=Decimal("0"),
        target_snapshot=Decimal("0"),
    )
    session.add(report)
    session.commit()

    ctx = build_sacs_context(report)
    assert ctx["private_reserve_balance"] == Decimal("0")
    assert ctx["schwab_balance"] == Decimal("0")
    assert ctx["has_client_2"] is False


def test_sacs_filename_is_safe(session):
    _, report = _seed_report(session)
    name = sacs_filename(report)
    assert name.endswith(".pdf")
    assert "SACS_" in name
    assert "2026-03-31" in name
    assert " " not in name


def test_sacs_template_renders_all_data_points(session):
    """Pure Jinja render — no WeasyPrint. Catches template bugs locally."""
    from app.services.pdf_generator import _env

    _, report = _seed_report(session)
    ctx = build_sacs_context(report)
    html = _env.get_template("sacs.html").render(**ctx)

    assert "Jane Doe &amp; John Doe" in html  # autoescaped ampersand
    assert "Simple Automated Cashflow System (SACS)" in html
    assert "INFLOW" in html
    assert "OUTFLOW" in html
    assert "PRIVATE" in html and "RESERVE" in html
    assert "FICA" in html
    assert "INVESTMENT" in html
    assert "MONTHLY CASHFLOW" in html
    assert "28th" in html
    assert "$15,000" in html  # inflow
    assert "$12,000" in html  # outflow
    assert "$3,000" in html   # excess
    assert "$75,000" in html  # FICA balance
    assert "$15,000+" in html  # investment with plus sign
    assert "6X Monthly Expenses + Deductibles" in html
    assert "Remainder" in html


# --- Render-path tests (require WeasyPrint) --------------------------------
@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_generate_sacs_pdf_returns_bytes(session):
    from app.services.pdf_generator import generate_sacs_pdf

    _, report = _seed_report(session)
    pdf_bytes = generate_sacs_pdf(report.id)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    # Guardrail: a reasonable SACS PDF is at least a few KB.
    assert len(pdf_bytes) > 2000


@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_generate_sacs_pdf_has_two_pages(session):
    from io import BytesIO

    import pypdf

    from app.services.pdf_generator import generate_sacs_pdf

    _, report = _seed_report(session)
    pdf_bytes = generate_sacs_pdf(report.id)

    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 2


@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_generate_sacs_pdf_stable_across_magnitudes(session):
    """Same shape of PDF should be produced for tiny and huge balances —
    layout containers are fixed-size, so byte count should not explode."""
    from app.services.pdf_generator import generate_sacs_pdf

    _, small_report = _seed_report(session, fica=5, schwab=3)
    small_bytes = generate_sacs_pdf(small_report.id)

    # New client to avoid unique constraints on the first seeded one.
    _, big_report = _seed_report(session, fica=9_999_999, schwab=1_234_567)
    big_bytes = generate_sacs_pdf(big_report.id)

    assert len(small_bytes) > 2000
    assert len(big_bytes) > 2000
    # Byte sizes should be within the same order of magnitude.
    ratio = max(len(small_bytes), len(big_bytes)) / min(
        len(small_bytes), len(big_bytes)
    )
    assert ratio < 1.3, f"PDF size drift too large (ratio={ratio:.2f})"


@pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
def test_sacs_route_returns_pdf_response(http, session):
    client, report = _seed_report(session)

    resp = http.get(f"/clients/{client.id}/reports/{report.id}/sacs.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF-")
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    assert "SACS_" in resp.headers.get("Content-Disposition", "")


def test_sacs_route_404_for_missing_report(http, app):
    # /clients/9999/reports/9999/sacs.pdf → 404, no WeasyPrint needed
    resp = http.get("/clients/9999/reports/9999/sacs.pdf")
    assert resp.status_code == 404
