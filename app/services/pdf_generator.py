"""PDF generation for quarterly reports.

Phase 4 = SACS, Phase 5 = TCC. Both PDFs are rendered from self-contained
HTML templates (inline CSS + inline SVG) so WeasyPrint does not need to
resolve external assets. We render via a dedicated Jinja environment rather
than Flask's `render_template` so PDF rendering can be invoked outside a
request context (CLI, background jobs, tests).
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.models import AccountCategory, AccountOwner, PersonRole, QuarterlyReport
from app.services.calculations import (
    calculate_c1_retirement,
    calculate_c2_retirement,
    calculate_excess,
    calculate_grand_total,
    calculate_inflow,
    calculate_liabilities_total,
    calculate_non_retirement_total,
)


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "pdf" / "templates"


def format_currency(value, decimals: int = 0) -> str:
    """Format a monetary value as "$X,XXX" (default) or "$X,XXX.XX".

    Negative values render as "-$X,XXX". None / empty → "$0".
    """
    if value is None or value == "":
        value = 0
    d = Decimal(str(value))
    negative = d < 0
    d = abs(d)
    if decimals == 0:
        rounded = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        core = f"{int(rounded):,}"
    else:
        quant = Decimal("1").scaleb(-decimals)
        rounded = d.quantize(quant, rounding=ROUND_HALF_UP)
        core = f"{rounded:,.{decimals}f}"
    return f"-${core}" if negative else f"${core}"


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
    )
    env.filters["currency"] = format_currency
    return env


_env = _build_env()


def _display_name(client) -> str:
    names = []
    for role in (PersonRole.CLIENT_1, PersonRole.CLIENT_2):
        person = client.person(role)
        if person and person.name:
            names.append(person.name)
    return " & ".join(names) if names else f"Client #{client.id}"


def _find_balance_for_report(report, account_predicate):
    """Return the balance this report snapshotted for the first account that
    matches the predicate, or Decimal(0) if none is present.
    """
    for bal in report.balances:
        acct = bal.account
        if acct is None:
            continue
        if account_predicate(acct):
            return Decimal(str(bal.balance or 0))
    return Decimal("0")


def _is_fica_account(acct) -> bool:
    if acct.category != AccountCategory.NON_RETIREMENT:
        return False
    type_ = (acct.type or "").lower()
    label = (acct.label or "").lower()
    return "fica" in type_ or "fica" in label


def _is_brokerage_account(acct) -> bool:
    if acct.category != AccountCategory.NON_RETIREMENT:
        return False
    type_ = (acct.type or "").lower()
    label = (acct.label or "").lower()
    return "brokerage" in type_ or "schwab" in label


def build_sacs_context(report) -> dict:
    """Shape the template inputs from a persisted QuarterlyReport snapshot."""
    client = report.client
    salary_c1 = Decimal(str(report.inflow_client_1_snapshot or 0))
    salary_c2 = Decimal(str(report.inflow_client_2_snapshot or 0))
    outflow = Decimal(str(report.outflow_snapshot or 0))
    inflow_total = calculate_inflow(salary_c1, salary_c2)
    excess = calculate_excess(inflow_total, outflow)

    private_reserve_balance = _find_balance_for_report(report, _is_fica_account)
    schwab_balance = _find_balance_for_report(report, _is_brokerage_account)

    return {
        "client_name": _display_name(client),
        "salary_c1": salary_c1,
        "salary_c2": salary_c2,
        "has_client_2": client.person(PersonRole.CLIENT_2) is not None,
        "inflow_total": inflow_total,
        "outflow": outflow,
        "excess": excess,
        "transfer_day": client.transfer_day_of_month,
        "private_reserve_balance": private_reserve_balance,
        "schwab_balance": schwab_balance,
        "report_date": report.report_date,
    }


def generate_sacs_pdf(report_id: int) -> bytes:
    """Render the SACS PDF for the given report. Raises ValueError if missing."""
    report = QuarterlyReport.query.get(report_id)
    if report is None:
        raise ValueError(f"Quarterly report {report_id} not found")

    context = build_sacs_context(report)
    template = _env.get_template("sacs.html")
    html_string = template.render(**context)

    # Lazy import so module import stays cheap and test discovery works
    # even when GTK libs aren't installed (pure-Python tests skip the
    # render path). GTK deps are provided by the Dockerfile.
    from weasyprint import HTML

    return HTML(string=html_string).write_pdf()


def sacs_filename(report) -> str:
    """Suggested download filename: SACS_Name_YYYY-MM-DD.pdf (safe characters only)."""
    return f"SACS_{_safe_name_slug(report.client)}_{_date_slug(report)}.pdf"


def tcc_filename(report) -> str:
    """Suggested download filename: TCC_Name_YYYY-MM-DD.pdf."""
    return f"TCC_{_safe_name_slug(report.client)}_{_date_slug(report)}.pdf"


def _safe_name_slug(client) -> str:
    raw = _display_name(client)
    safe = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in raw.replace(" & ", "_and_").replace(" ", "_")
    )
    return safe.strip("_") or "Client"


def _date_slug(report) -> str:
    return report.report_date.isoformat() if report.report_date else "report"


# ============================================================================
# TCC (Phase 5)
# ============================================================================
def _acct_entry(acct, bal) -> dict:
    """Shape an account bubble's data for the TCC template."""
    return {
        "last4": acct.account_number_last_4 or "",
        "type": acct.type or "",
        "label": acct.label or "",
        "balance": Decimal(str(bal.balance or 0)),
        "cash_balance": (
            Decimal(str(bal.cash_balance)) if bal.cash_balance is not None else None
        ),
        "as_of_date": bal.as_of_date,
        "is_outdated": bool(bal.is_outdated),
    }


def _liability_entry(liability) -> dict:
    return {
        "name": liability.name,
        "balance": Decimal(str(liability.balance or 0)),
        "as_of_date": liability.as_of_date,
    }


def group_tcc_accounts(report) -> dict:
    """Group account balances on this report by the 4-quadrant TCC layout.

    Joint non-retirement accounts are balanced into whichever side has fewer
    bubbles so visual fill stays even. Joint retirement is rare but gets
    bucketed under Client 1 if it appears.
    """
    client = report.client
    retirement_c1: list = []
    retirement_c2: list = []
    non_retirement_c1: list = []
    non_retirement_c2: list = []
    non_retirement_joint: list = []
    trust_entries: list = []

    for bal in report.balances:
        acct = bal.account
        if acct is None:
            continue
        entry = _acct_entry(acct, bal)
        if acct.category == AccountCategory.RETIREMENT:
            if acct.owner == AccountOwner.CLIENT_2:
                retirement_c2.append(entry)
            else:
                retirement_c1.append(entry)
        elif acct.category == AccountCategory.NON_RETIREMENT:
            if acct.owner == AccountOwner.CLIENT_1:
                non_retirement_c1.append(entry)
            elif acct.owner == AccountOwner.CLIENT_2:
                non_retirement_c2.append(entry)
            else:
                non_retirement_joint.append(entry)
        elif acct.category == AccountCategory.TRUST:
            trust_entries.append(entry)

    # Distribute joint accounts into whichever non-retirement side has room.
    for entry in non_retirement_joint:
        if len(non_retirement_c1) <= len(non_retirement_c2):
            non_retirement_c1.append(entry)
        else:
            non_retirement_c2.append(entry)

    trust_total = sum(
        (e["balance"] for e in trust_entries), Decimal("0")
    )
    trust_as_of = None
    if trust_entries:
        dates = [e["as_of_date"] for e in trust_entries if e["as_of_date"]]
        trust_as_of = max(dates) if dates else None

    return {
        "retirement_c1": retirement_c1,
        "retirement_c2": retirement_c2,
        "non_retirement_c1": non_retirement_c1,
        "non_retirement_c2": non_retirement_c2,
        "trust_total": trust_total,
        "trust_as_of": trust_as_of,
        "trust_accounts": trust_entries,
        "liabilities": [_liability_entry(l) for l in client.liabilities],
    }


def _person_view(person, report_date) -> dict | None:
    if person is None:
        return None
    age = None
    if person.dob and report_date:
        years = report_date.year - person.dob.year
        if (report_date.month, report_date.day) < (person.dob.month, person.dob.day):
            years -= 1
        age = max(years, 0)
    return {
        "name": person.name or "",
        "age": age,
        "dob": person.dob,
        "ssn_last_4": person.ssn_last_4 or "",
    }


def build_tcc_context(report) -> dict:
    """Assemble every value the TCC template needs."""
    client = report.client
    grouped = group_tcc_accounts(report)

    c1_retirement_total = calculate_c1_retirement(
        e["balance"] for e in grouped["retirement_c1"]
    )
    c2_retirement_total = calculate_c2_retirement(
        e["balance"] for e in grouped["retirement_c2"]
    )
    non_retirement_total = calculate_non_retirement_total(
        e["balance"]
        for e in grouped["non_retirement_c1"] + grouped["non_retirement_c2"]
    )
    grand_total = calculate_grand_total(
        c1_retirement_total,
        c2_retirement_total,
        non_retirement_total,
        grouped["trust_total"],
    )
    liabilities_total = calculate_liabilities_total(
        e["balance"] for e in grouped["liabilities"]
    )
    liabilities_as_of = None
    dates = [e["as_of_date"] for e in grouped["liabilities"] if e["as_of_date"]]
    if dates:
        liabilities_as_of = max(dates)

    any_outdated = any(
        e["is_outdated"]
        for bucket in (
            grouped["retirement_c1"],
            grouped["retirement_c2"],
            grouped["non_retirement_c1"],
            grouped["non_retirement_c2"],
            grouped["trust_accounts"],
        )
        for e in bucket
    )

    c1 = _person_view(client.person(PersonRole.CLIENT_1), report.report_date)
    c2 = _person_view(client.person(PersonRole.CLIENT_2), report.report_date)

    return {
        "client_name": _display_name(client),
        "report_date": report.report_date,
        "c1": c1,
        "c2": c2,
        "retirement_c1": grouped["retirement_c1"],
        "retirement_c2": grouped["retirement_c2"],
        "non_retirement_c1": grouped["non_retirement_c1"],
        "non_retirement_c2": grouped["non_retirement_c2"],
        "trust_total": grouped["trust_total"],
        "trust_as_of": grouped["trust_as_of"],
        "c1_retirement_total": c1_retirement_total,
        "c2_retirement_total": c2_retirement_total,
        "non_retirement_total": non_retirement_total,
        "grand_total": grand_total,
        "liabilities": grouped["liabilities"],
        "liabilities_total": liabilities_total,
        "liabilities_as_of": liabilities_as_of,
        "any_outdated": any_outdated,
    }


def _format_long_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.strftime("%B %d, %Y").replace(" 0", " ")
    return str(value)


def _format_short_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    return str(value)


_env.filters["long_date"] = _format_long_date
_env.filters["short_date"] = _format_short_date


def generate_tcc_pdf(report_id: int) -> bytes:
    """Render the TCC PDF for the given report. Raises ValueError if missing."""
    report = QuarterlyReport.query.get(report_id)
    if report is None:
        raise ValueError(f"Quarterly report {report_id} not found")

    context = build_tcc_context(report)
    template = _env.get_template("tcc.html")
    html_string = template.render(**context)

    from weasyprint import HTML

    return HTML(string=html_string).write_pdf()
