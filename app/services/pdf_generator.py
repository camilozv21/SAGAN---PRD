"""PDF generation for quarterly reports (Phase 4 = SACS).

`generate_sacs_pdf(report_id)` returns the rendered PDF bytes. The layout is
driven by `app/pdf/templates/sacs.html` — a self-contained HTML document
(inline CSS + inline SVG) so WeasyPrint does not need to resolve external
assets. We render via a dedicated Jinja environment rather than Flask's
`render_template` so PDF rendering can be invoked outside a request context
(CLI, background jobs, tests).
"""
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.models import AccountCategory, PersonRole, QuarterlyReport
from app.services.calculations import calculate_excess, calculate_inflow


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
    raw = _display_name(report.client)
    safe = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in raw.replace(" & ", "_and_").replace(" ", "_")
    )
    safe = safe.strip("_") or "Client"
    date_str = report.report_date.isoformat() if report.report_date else "report"
    return f"SACS_{safe}_{date_str}.pdf"
