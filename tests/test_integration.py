"""End-to-end integration tests (Phase 7).

Full flow: create client -> generate report -> download PDFs.
"""
from decimal import Decimal

import pytest

from app.models import (
    AccountCategory,
    Client,
    PersonRole,
    QuarterlyReport,
)

try:
    from weasyprint import HTML as _HTML  # noqa: F401
    WEASYPRINT_OK = True
    WEASYPRINT_SKIP_REASON = ""
except Exception as exc:
    WEASYPRINT_OK = False
    WEASYPRINT_SKIP_REASON = f"WeasyPrint native libs unavailable: {exc!s}"


def _create_married_client(http):
    """Create a full married client via the web form and return client_id."""
    payload = {
        "is_married": "on",
        "has_trust": "on",
        "property_address": "Integration Trust - 99 Test Dr",
        "transfer_day_of_month": "15",
        "notes": "Integration test household.",
        "c1_name": "Integ Client 1",
        "c1_dob": "1970-06-15",
        "c1_ssn_last_4": "1111",
        "c1_monthly_salary": "10000.00",
        "c2_name": "Integ Client 2",
        "c2_dob": "1972-03-20",
        "c2_ssn_last_4": "2222",
        "c2_monthly_salary": "8000.00",
        "retirement_owner[]": ["client_1", "client_2"],
        "retirement_type[]": ["Roth IRA", "401K"],
        "retirement_last4[]": ["1111", "2222"],
        "retirement_label[]": ["Roth IRA", "Corp 401K"],
        "nonret_owner[]": ["client_1", "client_1"],
        "nonret_type[]": ["FICA", "Brokerage"],
        "nonret_last4[]": ["3333", "4444"],
        "nonret_label[]": ["StoneCastle FICA", "Schwab Joint"],
        "liability_name[]": ["Mortgage"],
        "liability_rate[]": ["0.065"],
        "liability_balance[]": ["200000.00"],
        "insurance_type[]": ["Home", "Auto"],
        "insurance_deductible[]": ["2500.00", "1000.00"],
        "agreed_monthly_outflow": "12000.00",
        "private_reserve_target_override": "",
    }
    resp = http.post("/clients/", data=payload, follow_redirects=False)
    assert resp.status_code == 302, f"Failed to create client: {resp.status_code}"

    client = Client.query.order_by(Client.id.desc()).first()
    assert client is not None
    return client


def _create_report(http, client, *, report_date="2025-03-31"):
    """Create a quarterly report for the given client via form submission."""
    data = {
        "report_date": report_date,
        "salary_c1": "10000",
        "salary_c2": "8000",
        "outflow": "12000",
    }
    for account in client.accounts:
        prefix = f"account_{account.id}"
        data[f"{prefix}_balance"] = "50000"
        data[f"{prefix}_cash"] = ""
        data[f"{prefix}_as_of"] = report_date
    for liability in client.liabilities:
        prefix = f"liability_{liability.id}"
        data[f"{prefix}_balance"] = "200000"
        data[f"{prefix}_as_of"] = report_date

    resp = http.post(
        f"/clients/{client.id}/reports",
        data=data,
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), f"Report creation failed: {resp.status_code}"

    report = (
        QuarterlyReport.query
        .filter_by(client_id=client.id)
        .order_by(QuarterlyReport.id.desc())
        .first()
    )
    assert report is not None
    return report


class TestFullFlow:
    """Create client -> report -> verify detail -> download PDFs."""

    def test_create_client_and_report(self, app, session, http):
        client = _create_married_client(http)

        # Verify client structure
        assert client.is_married is True
        c1 = client.person(PersonRole.CLIENT_1)
        c2 = client.person(PersonRole.CLIENT_2)
        assert c1.name == "Integ Client 1"
        assert c2.name == "Integ Client 2"
        assert len(client.accounts) == 5  # 2 retirement + 2 non-ret + 1 trust

        # Create report
        report = _create_report(http, client)
        assert report.report_date.isoformat() == "2025-03-31"
        assert float(report.inflow_client_1_snapshot) == 10000.0
        assert float(report.outflow_snapshot) == 12000.0

    def test_report_detail_page_shows_download_buttons(self, app, session, http):
        client = _create_married_client(http)
        report = _create_report(http, client)

        resp = http.get(f"/clients/{client.id}/reports/{report.id}")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Download SACS PDF" in body
        assert "Download TCC PDF" in body
        assert "Download Both (ZIP)" in body

    @pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
    def test_sacs_pdf_downloads(self, app, session, http):
        client = _create_married_client(http)
        report = _create_report(http, client)

        resp = http.get(f"/clients/{client.id}/reports/{report.id}/sacs.pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert resp.data.startswith(b"%PDF-")

    @pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
    def test_tcc_pdf_downloads(self, app, session, http):
        client = _create_married_client(http)
        report = _create_report(http, client)

        resp = http.get(f"/clients/{client.id}/reports/{report.id}/tcc.pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert resp.data.startswith(b"%PDF-")

    @pytest.mark.skipif(not WEASYPRINT_OK, reason=WEASYPRINT_SKIP_REASON)
    def test_zip_pdf_downloads(self, app, session, http):
        import io
        import zipfile

        client = _create_married_client(http)
        report = _create_report(http, client)

        resp = http.get(f"/clients/{client.id}/reports/{report.id}/both.zip")
        assert resp.status_code == 200
        assert resp.mimetype == "application/zip"
        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            names = zf.namelist()
        assert any(n.startswith("SACS_") for n in names)
        assert any(n.startswith("TCC_") for n in names)


class TestMultipleReports:
    """Verify that creating multiple reports preserves each snapshot."""

    def test_two_reports_have_independent_snapshots(self, app, session, http):
        client = _create_married_client(http)

        # Report 1 with balances = 50000
        report_1 = _create_report(http, client, report_date="2025-01-15")

        # Report 2 with different balances
        data_2 = {
            "report_date": "2025-04-15",
            "salary_c1": "11000",
            "salary_c2": "9000",
            "outflow": "14000",
        }
        for account in client.accounts:
            prefix = f"account_{account.id}"
            data_2[f"{prefix}_balance"] = "75000"
            data_2[f"{prefix}_cash"] = ""
            data_2[f"{prefix}_as_of"] = "2025-04-15"
        for liability in client.liabilities:
            prefix = f"liability_{liability.id}"
            data_2[f"{prefix}_balance"] = "195000"
            data_2[f"{prefix}_as_of"] = "2025-04-15"
        http.post(f"/clients/{client.id}/reports", data=data_2, follow_redirects=False)

        report_2 = (
            QuarterlyReport.query
            .filter_by(client_id=client.id)
            .order_by(QuarterlyReport.id.desc())
            .first()
        )

        # Verify report 1 snapshot is untouched
        from app.models import AccountBalance
        session.refresh(report_1)
        assert float(report_1.inflow_client_1_snapshot) == 10000.0
        r1_balances = AccountBalance.query.filter_by(report_id=report_1.id).all()
        for bal in r1_balances:
            assert float(bal.balance) == 50000.0

        # Verify report 2 has its own values
        assert float(report_2.inflow_client_1_snapshot) == 11000.0
        r2_balances = AccountBalance.query.filter_by(report_id=report_2.id).all()
        for bal in r2_balances:
            assert float(bal.balance) == 75000.0
