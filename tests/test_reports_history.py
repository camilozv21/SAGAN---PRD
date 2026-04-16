"""Phase 6 tests: report history, immutable snapshots, ZIP download."""
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


# --- Helpers ----------------------------------------------------------------

def _seed_client(session):
    """Create a married client with accounts, liabilities, insurance."""
    client = Client(
        property_address="Test Trust - 123 Oak St",
        transfer_day_of_month=28,
    )
    session.add(client)
    session.flush()

    client.people.append(Person(
        role=PersonRole.CLIENT_1,
        name="Alice Test",
        monthly_salary=Decimal("8000"),
    ))
    client.people.append(Person(
        role=PersonRole.CLIENT_2,
        name="Bob Test",
        monthly_salary=Decimal("7000"),
    ))

    client.static_financials = StaticFinancials(
        agreed_monthly_outflow=Decimal("10000"),
    )

    client.insurance_policies.append(
        InsurancePolicy(type="Home", deductible=Decimal("2500")),
    )

    # Retirement C1
    acct_ret_c1 = Account(
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.RETIREMENT,
        type="Roth IRA",
        label="Roth IRA",
    )
    client.accounts.append(acct_ret_c1)

    # Retirement C2
    acct_ret_c2 = Account(
        owner=AccountOwner.CLIENT_2,
        category=AccountCategory.RETIREMENT,
        type="401K",
        label="401K",
    )
    client.accounts.append(acct_ret_c2)

    # Non-retirement
    acct_fica = Account(
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT,
        type="FICA",
        label="FICA Account",
    )
    client.accounts.append(acct_fica)

    acct_brok = Account(
        owner=AccountOwner.CLIENT_1,
        category=AccountCategory.NON_RETIREMENT,
        type="Brokerage",
        label="Schwab",
    )
    client.accounts.append(acct_brok)

    # Trust
    acct_trust = Account(
        owner=AccountOwner.JOINT,
        category=AccountCategory.TRUST,
        type="Trust",
        label="Family Trust",
    )
    client.accounts.append(acct_trust)

    # Liabilities
    client.liabilities.append(
        Liability(name="Mortgage", balance=Decimal("200000"), interest_rate=Decimal("0.065")),
    )

    session.commit()
    return client


def _report_form_data(client, *, report_date="2025-01-15",
                      salary_c1="8000", salary_c2="7000", outflow="10000",
                      balances=None):
    """Build the form payload for creating a report."""
    if balances is None:
        balances = {}

    data = {
        "report_date": report_date,
        "salary_c1": salary_c1,
        "salary_c2": salary_c2,
        "outflow": outflow,
    }

    for account in client.accounts:
        prefix = f"account_{account.id}"
        acct_bal = balances.get(account.id, {})
        data[f"{prefix}_balance"] = str(acct_bal.get("balance", "10000"))
        data[f"{prefix}_cash"] = str(acct_bal.get("cash", ""))
        data[f"{prefix}_as_of"] = acct_bal.get("as_of", "2025-01-15")
        if acct_bal.get("outdated"):
            data[f"{prefix}_outdated"] = "on"

    for liability in client.liabilities:
        prefix = f"liability_{liability.id}"
        data[f"{prefix}_balance"] = str(liability.balance)
        data[f"{prefix}_as_of"] = "2025-01-15"

    return data


# --- Tests ------------------------------------------------------------------

class TestReportHistory:
    """Reports appear in the client detail history, ordered by date descending."""

    def test_three_reports_appear_in_order(self, app, session, http):
        client = _seed_client(session)

        # Create 3 reports with different dates
        for date_str in ["2025-01-15", "2025-04-15", "2025-07-15"]:
            data = _report_form_data(client, report_date=date_str)
            resp = http.post(
                f"/clients/{client.id}/reports",
                data=data,
                follow_redirects=False,
            )
            assert resp.status_code in (302, 303), f"Failed to create report for {date_str}"

        reports = (
            QuarterlyReport.query
            .filter_by(client_id=client.id)
            .order_by(QuarterlyReport.report_date.desc())
            .all()
        )
        assert len(reports) == 3
        dates = [r.report_date.isoformat() for r in reports]
        assert dates == ["2025-07-15", "2025-04-15", "2025-01-15"]

    def test_reports_visible_on_client_detail(self, app, session, http):
        client = _seed_client(session)
        data = _report_form_data(client, report_date="2025-03-01")
        http.post(f"/clients/{client.id}/reports", data=data, follow_redirects=True)

        resp = http.get(f"/clients/{client.id}")
        assert resp.status_code == 200
        assert b"2025-03-01" in resp.data
        assert b"Reports history" in resp.data


class TestSnapshotImmutability:
    """Modifying client data after report creation must not affect old reports."""

    def test_old_report_keeps_original_balances(self, app, session, http):
        client = _seed_client(session)

        # Create the first report with known balances
        custom_balances = {}
        for acct in client.accounts:
            custom_balances[acct.id] = {"balance": "50000", "as_of": "2025-01-15"}

        data = _report_form_data(
            client,
            report_date="2025-01-15",
            salary_c1="8000",
            salary_c2="7000",
            outflow="10000",
            balances=custom_balances,
        )
        resp = http.post(f"/clients/{client.id}/reports", data=data, follow_redirects=False)
        assert resp.status_code in (302, 303)

        report_1 = QuarterlyReport.query.filter_by(client_id=client.id).first()
        assert report_1 is not None

        # Verify the snapshotted values
        assert float(report_1.inflow_client_1_snapshot) == 8000.0
        assert float(report_1.outflow_snapshot) == 10000.0

        # Check that AccountBalances are tied to this report
        balances = AccountBalance.query.filter_by(report_id=report_1.id).all()
        assert len(balances) == len(client.accounts)
        for bal in balances:
            assert float(bal.balance) == 50000.0

        # Now create a second report with DIFFERENT balances
        custom_balances_2 = {}
        for acct in client.accounts:
            custom_balances_2[acct.id] = {"balance": "99999", "as_of": "2025-04-15"}

        data2 = _report_form_data(
            client,
            report_date="2025-04-15",
            salary_c1="12000",
            salary_c2="9000",
            outflow="15000",
            balances=custom_balances_2,
        )
        resp2 = http.post(f"/clients/{client.id}/reports", data=data2, follow_redirects=False)
        assert resp2.status_code in (302, 303)

        # Verify old report's balances are UNCHANGED
        old_balances = AccountBalance.query.filter_by(report_id=report_1.id).all()
        for bal in old_balances:
            assert float(bal.balance) == 50000.0, (
                f"Old report balance changed! Got {bal.balance} for account {bal.account_id}"
            )

        # Verify old report's snapshot fields are unchanged
        session.refresh(report_1)
        assert float(report_1.inflow_client_1_snapshot) == 8000.0
        assert float(report_1.outflow_snapshot) == 10000.0

    def test_liability_snapshot_preserved(self, app, session, http):
        client = _seed_client(session)
        data = _report_form_data(client, report_date="2025-01-15")
        http.post(f"/clients/{client.id}/reports", data=data, follow_redirects=False)

        report = QuarterlyReport.query.filter_by(client_id=client.id).first()
        liab_snap = report.get_liabilities_snapshot()
        assert liab_snap is not None
        assert len(liab_snap) == 1
        assert liab_snap[0]["name"] == "Mortgage"
        assert float(liab_snap[0]["balance"]) == 200000.0


class TestZipDownload:
    """The both.zip endpoint returns a valid ZIP."""

    def test_zip_download_returns_zip(self, app, session, http):
        client = _seed_client(session)
        data = _report_form_data(client, report_date="2025-01-15")
        http.post(f"/clients/{client.id}/reports", data=data, follow_redirects=False)

        report = QuarterlyReport.query.filter_by(client_id=client.id).first()

        resp = http.get(f"/clients/{client.id}/reports/{report.id}/both.zip")

        if resp.status_code == 302:
            # WeasyPrint not available — route caught the error and redirected
            import pytest
            pytest.skip("WeasyPrint not available in test environment")

        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        assert b"PK" in resp.data[:4]  # ZIP magic bytes


class TestReportDetail:
    """The report detail page shows correct data."""

    def test_detail_page_renders(self, app, session, http):
        client = _seed_client(session)
        data = _report_form_data(client, report_date="2025-02-28")
        http.post(f"/clients/{client.id}/reports", data=data, follow_redirects=False)

        report = QuarterlyReport.query.filter_by(client_id=client.id).first()
        resp = http.get(f"/clients/{client.id}/reports/{report.id}")
        assert resp.status_code == 200
        assert b"2025-02-28" in resp.data
        assert b"Download SACS PDF" in resp.data
        assert b"Download TCC PDF" in resp.data
        assert b"Download Both (ZIP)" in resp.data
        assert b"Export to Canva" in resp.data

    def test_form_snapshot_page_renders(self, app, session, http):
        client = _seed_client(session)
        data = _report_form_data(client, report_date="2025-02-28")
        http.post(f"/clients/{client.id}/reports", data=data, follow_redirects=False)

        report = QuarterlyReport.query.filter_by(client_id=client.id).first()
        resp = http.get(f"/clients/{client.id}/reports/{report.id}/form")
        assert resp.status_code == 200
        assert b"Original form data" in resp.data
