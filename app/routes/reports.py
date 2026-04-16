"""Quarterly report entry (Phase 3).

Routes:
    GET  /clients/<id>/new-report       - balance entry form
    POST /clients/<id>/reports          - persist snapshot
    GET  /clients/<id>/reports/<rid>    - placeholder view (Phase 6)
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db
from app.models import (
    AccountBalance,
    AccountCategory,
    AccountOwner,
    Client,
    PersonRole,
    QuarterlyReport,
)
from app.services.calculations import calculate_target

reports_bp = Blueprint("reports", __name__, url_prefix="/clients/<int:client_id>")


# --- Parsers ---------------------------------------------------------------
def _parse_decimal(raw, *, field, errors, required=False, min_value=None):
    if raw is None or str(raw).strip() == "":
        if required:
            errors.append(f"{field}: required.")
        return None
    try:
        value = Decimal(str(raw).replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        errors.append(f"{field}: invalid number.")
        return None
    if min_value is not None and value < min_value:
        errors.append(f"{field}: must be >= {min_value}.")
        return None
    return value


def _parse_date(raw, *, field, errors, required=False):
    if raw is None or str(raw).strip() == "":
        if required:
            errors.append(f"{field}: required.")
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except (ValueError, TypeError):
        errors.append(f"{field}: invalid date (expected YYYY-MM-DD).")
        return None


# --- View helpers ----------------------------------------------------------
def _client_display_name(client):
    c1 = client.person(PersonRole.CLIENT_1)
    c2 = client.person(PersonRole.CLIENT_2)
    names = [p.name for p in [c1, c2] if p is not None and p.name]
    return " & ".join(names) if names else f"Client #{client.id}"


def _account_hint(account):
    latest = account.latest_balance
    if latest is None:
        return None
    return {
        "balance": str(latest.balance),
        "cash_balance": (
            str(latest.cash_balance) if latest.cash_balance is not None else ""
        ),
        "as_of_date": latest.as_of_date.isoformat() if latest.as_of_date else "",
        "is_outdated": bool(latest.is_outdated),
    }


def _account_view(account):
    return {
        "id": account.id,
        "owner": account.owner.value,
        "type": account.type,
        "label": account.label or "",
        "last4": account.account_number_last_4 or "",
        "hint": _account_hint(account),
    }


def _liability_view(liability):
    return {
        "id": liability.id,
        "name": liability.name,
        "balance": str(liability.balance) if liability.balance is not None else "",
        "as_of_date": (
            liability.as_of_date.isoformat() if liability.as_of_date else ""
        ),
    }


def _build_form_context(client, *, form_values=None):
    """Context for rendering entry_form.html (GET + POST-with-errors)."""
    c1 = client.person(PersonRole.CLIENT_1)
    c2 = client.person(PersonRole.CLIENT_2)
    sf = client.static_financials

    c1_salary = str(c1.monthly_salary) if c1 and c1.monthly_salary is not None else "0"
    c2_salary = str(c2.monthly_salary) if c2 and c2.monthly_salary is not None else "0"
    outflow = (
        str(sf.agreed_monthly_outflow)
        if sf and sf.agreed_monthly_outflow is not None
        else "0"
    )

    c1_retirement = [
        _account_view(a) for a in client.accounts
        if a.category == AccountCategory.RETIREMENT
        and a.owner == AccountOwner.CLIENT_1
    ]
    c2_retirement = [
        _account_view(a) for a in client.accounts
        if a.category == AccountCategory.RETIREMENT
        and a.owner == AccountOwner.CLIENT_2
    ]
    non_retirement = [
        _account_view(a) for a in client.accounts
        if a.category == AccountCategory.NON_RETIREMENT
    ]
    trust_accounts = [
        _account_view(a) for a in client.accounts
        if a.category == AccountCategory.TRUST
    ]

    deductibles = [str(p.deductible) for p in client.insurance_policies]

    return {
        "client": client,
        "display_name": _client_display_name(client),
        "c1_name": (c1.name if c1 else "Client 1"),
        "c2_name": (c2.name if c2 else None),
        "is_married": client.is_married,
        "c1_salary_default": c1_salary,
        "c2_salary_default": c2_salary,
        "outflow_default": outflow,
        "transfer_day": client.transfer_day_of_month,
        "deductibles": deductibles,
        "c1_retirement": c1_retirement,
        "c2_retirement": c2_retirement,
        "non_retirement": non_retirement,
        "trust_accounts": trust_accounts,
        "liabilities": [_liability_view(l) for l in client.liabilities],
        "report_date_default": date.today().isoformat(),
        "form_values": form_values or {},
    }


# --- Routes ----------------------------------------------------------------
@reports_bp.route("/new-report", methods=["GET"])
def new_report(client_id):
    client = Client.query.get(client_id)
    if client is None:
        abort(404)
    return render_template(
        "reports/entry_form.html",
        **_build_form_context(client),
    )


@reports_bp.route("/reports", methods=["POST"])
def create_report(client_id):
    client = Client.query.get(client_id)
    if client is None:
        abort(404)

    form = request.form
    errors = []

    report_date = _parse_date(
        form.get("report_date"), field="Report date",
        errors=errors, required=True,
    )
    salary_c1 = _parse_decimal(
        form.get("salary_c1"), field="Client 1 monthly salary",
        errors=errors, required=True, min_value=Decimal("0"),
    )
    if client.is_married:
        salary_c2 = _parse_decimal(
            form.get("salary_c2"), field="Client 2 monthly salary",
            errors=errors, required=True, min_value=Decimal("0"),
        )
    else:
        salary_c2 = Decimal("0")
    outflow = _parse_decimal(
        form.get("outflow"), field="Monthly outflow",
        errors=errors, required=True, min_value=Decimal("0"),
    )

    # Per-account balance parsing. Every account owned by the client needs
    # a fresh balance, cash (optional), and as-of date.
    account_inputs = {}
    for account in client.accounts:
        label = account.label or account.type
        prefix = f"account_{account.id}"
        balance = _parse_decimal(
            form.get(f"{prefix}_balance"),
            field=f"Balance for '{label}'",
            errors=errors, required=True, min_value=Decimal("0"),
        )
        cash_balance = _parse_decimal(
            form.get(f"{prefix}_cash"),
            field=f"Cash balance for '{label}'",
            errors=errors, min_value=Decimal("0"),
        )
        as_of = _parse_date(
            form.get(f"{prefix}_as_of"),
            field=f"As-of date for '{label}'",
            errors=errors, required=True,
        )
        account_inputs[account.id] = {
            "balance": balance,
            "cash_balance": cash_balance,
            "as_of_date": as_of,
            "is_outdated": form.get(f"{prefix}_outdated") == "on",
        }

    # Liabilities: balance is required (we update the live row).
    liability_inputs = {}
    for liability in client.liabilities:
        prefix = f"liability_{liability.id}"
        balance = _parse_decimal(
            form.get(f"{prefix}_balance"),
            field=f"Balance for liability '{liability.name}'",
            errors=errors, required=True, min_value=Decimal("0"),
        )
        as_of = _parse_date(
            form.get(f"{prefix}_as_of"),
            field=f"As-of date for liability '{liability.name}'",
            errors=errors,
        )
        liability_inputs[liability.id] = {"balance": balance, "as_of_date": as_of}

    if errors:
        for err in errors:
            flash(err, "error")
        return (
            render_template(
                "reports/entry_form.html",
                **_build_form_context(client, form_values=dict(form)),
            ),
            400,
        )

    trust_total = sum(
        (
            account_inputs[a.id]["balance"]
            for a in client.accounts
            if a.category == AccountCategory.TRUST
        ),
        Decimal("0"),
    )
    deductibles = [p.deductible for p in client.insurance_policies]
    target = calculate_target(outflow, deductibles)

    report = QuarterlyReport(
        client_id=client.id,
        report_date=report_date,
        inflow_client_1_snapshot=salary_c1,
        inflow_client_2_snapshot=salary_c2,
        outflow_snapshot=outflow,
        trust_value_snapshot=trust_total,
        target_snapshot=target,
    )
    db.session.add(report)
    db.session.flush()  # need report.id for FK on AccountBalance

    for account in client.accounts:
        inp = account_inputs[account.id]
        db.session.add(AccountBalance(
            account_id=account.id,
            report_id=report.id,
            balance=inp["balance"],
            cash_balance=inp["cash_balance"],
            as_of_date=inp["as_of_date"],
            is_outdated=inp["is_outdated"],
        ))

    for liability in client.liabilities:
        inp = liability_inputs[liability.id]
        liability.balance = inp["balance"]
        if inp["as_of_date"] is not None:
            liability.as_of_date = inp["as_of_date"]

    try:
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Could not save report: {exc}", "error")
        return (
            render_template(
                "reports/entry_form.html",
                **_build_form_context(client, form_values=dict(form)),
            ),
            400,
        )

    flash("Report saved.", "success")
    return redirect(
        url_for("reports.view_report", client_id=client.id, report_id=report.id)
    )


@reports_bp.route("/reports/<int:report_id>", methods=["GET"])
def view_report(client_id, report_id):
    client = Client.query.get(client_id)
    if client is None:
        abort(404)
    report = QuarterlyReport.query.get(report_id)
    if report is None or report.client_id != client.id:
        abort(404)
    return render_template(
        "reports/view_placeholder.html",
        client=client,
        display_name=_client_display_name(client),
        report=report,
    )
