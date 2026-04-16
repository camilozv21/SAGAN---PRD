"""Client CRUD (Phase 2).

Routes:
    GET  /clients               - list
    GET  /clients/new           - creation form
    POST /clients               - create
    GET  /clients/<id>          - read-only detail
    GET  /clients/<id>/edit     - edit form
    POST /clients/<id>          - update
    POST /clients/<id>/delete   - delete
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
    Account,
    AccountCategory,
    AccountOwner,
    Client,
    InsurancePolicy,
    Liability,
    Person,
    PersonRole,
    StaticFinancials,
)

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


# --- Dropdown options (values accepted by the form) ------------------------
RETIREMENT_TYPES = ["IRA", "Roth IRA", "401K", "Pension", "Other"]
NON_RETIREMENT_TYPES = ["Brokerage", "Checking", "Savings", "FICA", "Other"]
INSURANCE_TYPES = ["Home", "Auto", "Health", "Umbrella", "Life", "Other"]


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


def _parse_int(raw, *, field, errors, required=False, min_value=None, max_value=None):
    if raw is None or str(raw).strip() == "":
        if required:
            errors.append(f"{field}: required.")
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        errors.append(f"{field}: invalid number.")
        return None
    if min_value is not None and value < min_value:
        errors.append(f"{field}: must be >= {min_value}.")
        return None
    if max_value is not None and value > max_value:
        errors.append(f"{field}: must be <= {max_value}.")
        return None
    return value


def _parse_date(raw, *, field, errors, required=False):
    if raw is None or str(raw).strip() == "":
        if required:
            errors.append(f"{field}: required.")
        return None
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, TypeError, AttributeError):
        errors.append(f"{field}: invalid date (expected YYYY-MM-DD).")
        return None


def _parse_ssn(raw, *, field, errors):
    if raw is None or str(raw).strip() == "":
        return None
    val = str(raw).strip()
    if not (val.isdigit() and len(val) == 4):
        errors.append(f"{field}: must be exactly 4 digits.")
        return None
    return val


def _parse_str(raw, *, field, errors, required=False, max_len=None):
    if raw is None or str(raw).strip() == "":
        if required:
            errors.append(f"{field}: required.")
        return None
    val = str(raw).strip()
    if max_len is not None and len(val) > max_len:
        errors.append(f"{field}: max {max_len} characters.")
        return None
    return val


def _zip_rows(form, keys):
    """Return list of dicts aligning `form.getlist(k)` for each k in keys."""
    columns = {k: form.getlist(f"{k}[]") for k in keys}
    length = max((len(v) for v in columns.values()), default=0)
    rows = []
    for i in range(length):
        rows.append({k: (columns[k][i] if i < len(columns[k]) else "") for k in keys})
    return rows


def _row_is_empty(row):
    return all((v is None or str(v).strip() == "") for v in row.values())


# --- Full form parsing -----------------------------------------------------
def _parse_client_form(form):
    """Extract and validate the full form. Returns (data, errors)."""
    errors = []
    data = {}

    # --- Basic ----------------------------------------------------------
    is_married = form.get("is_married") == "on"
    data["is_married"] = is_married
    data["property_address"] = _parse_str(
        form.get("property_address"), field="Property address",
        errors=errors, max_len=255,
    )
    data["transfer_day_of_month"] = _parse_int(
        form.get("transfer_day_of_month"), field="Transfer day",
        errors=errors, required=True, min_value=1, max_value=31,
    )
    data["notes"] = _parse_str(form.get("notes"), field="Notes", errors=errors)
    data["has_trust"] = form.get("has_trust") == "on"

    # --- People ---------------------------------------------------------
    data["client_1"] = {
        "name": _parse_str(form.get("c1_name"), field="Client 1 name",
                           errors=errors, required=True, max_len=120),
        "dob": _parse_date(form.get("c1_dob"), field="Client 1 DOB", errors=errors),
        "ssn_last_4": _parse_ssn(form.get("c1_ssn_last_4"),
                                  field="Client 1 SSN", errors=errors),
        "monthly_salary": _parse_decimal(
            form.get("c1_monthly_salary"), field="Client 1 monthly salary",
            errors=errors, required=True, min_value=Decimal("0"),
        ),
    }
    if is_married:
        data["client_2"] = {
            "name": _parse_str(form.get("c2_name"), field="Client 2 name",
                               errors=errors, required=True, max_len=120),
            "dob": _parse_date(form.get("c2_dob"), field="Client 2 DOB",
                               errors=errors),
            "ssn_last_4": _parse_ssn(form.get("c2_ssn_last_4"),
                                      field="Client 2 SSN", errors=errors),
            "monthly_salary": _parse_decimal(
                form.get("c2_monthly_salary"), field="Client 2 monthly salary",
                errors=errors, required=True, min_value=Decimal("0"),
            ),
        }
    else:
        data["client_2"] = None

    # --- Retirement accounts -------------------------------------------
    data["retirement"] = []
    for i, row in enumerate(_zip_rows(form, ["retirement_owner", "retirement_type",
                                              "retirement_last4", "retirement_label"]), 1):
        if _row_is_empty(row):
            continue
        owner_raw = row["retirement_owner"]
        type_raw = row["retirement_type"]
        if owner_raw not in ("client_1", "client_2"):
            errors.append(f"Retirement account #{i}: invalid owner.")
            continue
        if not is_married and owner_raw == "client_2":
            errors.append(
                f"Retirement account #{i}: a single household cannot own "
                "Client 2 accounts."
            )
            continue
        if type_raw not in RETIREMENT_TYPES:
            errors.append(f"Retirement account #{i}: invalid type.")
            continue
        last4 = _parse_str(row["retirement_last4"],
                           field=f"Retirement account #{i} last 4",
                           errors=errors, max_len=8)
        label = _parse_str(row["retirement_label"],
                           field=f"Retirement account #{i} label",
                           errors=errors, max_len=160)
        data["retirement"].append({
            "owner": AccountOwner(owner_raw),
            "type": type_raw,
            "account_number_last_4": last4,
            "label": label,
        })

    # --- Non-retirement accounts ---------------------------------------
    data["non_retirement"] = []
    for i, row in enumerate(_zip_rows(form, ["nonret_owner", "nonret_type",
                                              "nonret_last4", "nonret_label"]), 1):
        if _row_is_empty(row):
            continue
        owner_raw = row["nonret_owner"]
        type_raw = row["nonret_type"]
        if owner_raw not in ("client_1", "client_2", "joint"):
            errors.append(f"Non-retirement account #{i}: invalid owner.")
            continue
        if not is_married and owner_raw == "client_2":
            errors.append(
                f"Non-retirement account #{i}: a single household cannot own "
                "Client 2 accounts."
            )
            continue
        if type_raw not in NON_RETIREMENT_TYPES:
            errors.append(f"Non-retirement account #{i}: invalid type.")
            continue
        last4 = _parse_str(row["nonret_last4"],
                           field=f"Non-retirement account #{i} last 4",
                           errors=errors, max_len=8)
        label = _parse_str(row["nonret_label"],
                           field=f"Non-retirement account #{i} label",
                           errors=errors, max_len=160)
        data["non_retirement"].append({
            "owner": AccountOwner(owner_raw),
            "type": type_raw,
            "account_number_last_4": last4,
            "label": label,
        })

    # --- Liabilities ---------------------------------------------------
    data["liabilities"] = []
    for i, row in enumerate(_zip_rows(form, ["liability_name", "liability_rate",
                                              "liability_balance"]), 1):
        if _row_is_empty(row):
            continue
        name = _parse_str(row["liability_name"], field=f"Liability #{i} name",
                          errors=errors, required=True, max_len=120)
        rate = _parse_decimal(row["liability_rate"],
                              field=f"Liability #{i} rate", errors=errors,
                              min_value=Decimal("0"))
        balance = _parse_decimal(row["liability_balance"],
                                 field=f"Liability #{i} balance", errors=errors,
                                 min_value=Decimal("0"))
        data["liabilities"].append({
            "name": name,
            "interest_rate": rate,
            "balance": balance if balance is not None else Decimal("0"),
        })

    # --- Insurance policies --------------------------------------------
    data["insurance"] = []
    for i, row in enumerate(_zip_rows(form, ["insurance_type",
                                              "insurance_deductible"]), 1):
        if _row_is_empty(row):
            continue
        type_raw = _parse_str(row["insurance_type"], field=f"Policy #{i} type",
                              errors=errors, required=True, max_len=60)
        deductible = _parse_decimal(row["insurance_deductible"],
                                    field=f"Policy #{i} deductible",
                                    errors=errors, required=True,
                                    min_value=Decimal("0"))
        data["insurance"].append({"type": type_raw, "deductible": deductible})

    # --- Static financials ---------------------------------------------
    data["agreed_monthly_outflow"] = _parse_decimal(
        form.get("agreed_monthly_outflow"), field="Agreed monthly outflow",
        errors=errors, required=True, min_value=Decimal("0"),
    )
    data["private_reserve_target_override"] = _parse_decimal(
        form.get("private_reserve_target_override"),
        field="Private reserve target override", errors=errors,
        min_value=Decimal("0"),
    )

    return data, errors


# --- Apply parsed data to a Client ----------------------------------------
def _apply_to_client(client, data, *, is_new):
    """Apply (already validated) `data` to `client`.

    Children (accounts, liabilities, insurance) use a wipe + recreate strategy.
    Phase 2 does not persist quarterly balances yet, so wiping is safe.
    """
    client.property_address = data["property_address"]
    client.transfer_day_of_month = data["transfer_day_of_month"]
    client.notes = data["notes"]

    # --- People: upsert by role, drop C2 if the household is now single -
    c1 = client.person(PersonRole.CLIENT_1) if not is_new else None
    if c1 is None:
        c1 = Person(role=PersonRole.CLIENT_1)
        client.people.append(c1)
    c1.name = data["client_1"]["name"]
    c1.dob = data["client_1"]["dob"]
    c1.ssn_last_4 = data["client_1"]["ssn_last_4"]
    c1.monthly_salary = data["client_1"]["monthly_salary"]

    existing_c2 = client.person(PersonRole.CLIENT_2) if not is_new else None
    if data["is_married"]:
        c2 = existing_c2
        if c2 is None:
            c2 = Person(role=PersonRole.CLIENT_2)
            client.people.append(c2)
        c2.name = data["client_2"]["name"]
        c2.dob = data["client_2"]["dob"]
        c2.ssn_last_4 = data["client_2"]["ssn_last_4"]
        c2.monthly_salary = data["client_2"]["monthly_salary"]
    elif existing_c2 is not None:
        client.people.remove(existing_c2)

    # --- Accounts / Liabilities / Insurance: wipe + recreate -----------
    for acct in list(client.accounts):
        client.accounts.remove(acct)
    for liab in list(client.liabilities):
        client.liabilities.remove(liab)
    for pol in list(client.insurance_policies):
        client.insurance_policies.remove(pol)

    for spec in data["retirement"]:
        client.accounts.append(Account(
            owner=spec["owner"],
            category=AccountCategory.RETIREMENT,
            type=spec["type"],
            account_number_last_4=spec["account_number_last_4"],
            label=spec["label"],
        ))
    for spec in data["non_retirement"]:
        client.accounts.append(Account(
            owner=spec["owner"],
            category=AccountCategory.NON_RETIREMENT,
            type=spec["type"],
            account_number_last_4=spec["account_number_last_4"],
            label=spec["label"],
        ))
    if data["has_trust"]:
        client.accounts.append(Account(
            owner=AccountOwner.JOINT,
            category=AccountCategory.TRUST,
            type="Trust",
            label=data["property_address"] or "Family Trust",
        ))

    for spec in data["liabilities"]:
        client.liabilities.append(Liability(
            name=spec["name"],
            interest_rate=spec["interest_rate"],
            balance=spec["balance"],
        ))
    for spec in data["insurance"]:
        client.insurance_policies.append(InsurancePolicy(
            type=spec["type"], deductible=spec["deductible"],
        ))

    # --- Static financials (uselist=False) ------------------------------
    sf = client.static_financials
    if sf is None:
        sf = StaticFinancials()
        client.static_financials = sf
    sf.agreed_monthly_outflow = data["agreed_monthly_outflow"]
    sf.private_reserve_target_override = data["private_reserve_target_override"]


# --- View helpers ----------------------------------------------------------
def _client_display_name(client):
    c1 = client.person(PersonRole.CLIENT_1)
    c2 = client.person(PersonRole.CLIENT_2)
    names = [p.name for p in [c1, c2] if p is not None and p.name]
    return " & ".join(names) if names else f"Client #{client.id}"


def _last_report_date(client):
    dates = [r.report_date for r in client.quarterly_reports if r.report_date]
    return max(dates) if dates else None


def _values_from_form(form):
    """Normalize request.form into a dict shaped {field: str | list[dict]}.

    Used to re-render the form after server-side validation errors.
    """
    def rows(keys, strip_prefix):
        result = []
        for row in _zip_rows(form, keys):
            result.append({k[len(strip_prefix):]: row[k] for k in keys})
        return result

    return {
        "is_married": form.get("is_married") == "on",
        "has_trust": form.get("has_trust") == "on",
        "property_address": form.get("property_address", ""),
        "transfer_day_of_month": form.get("transfer_day_of_month", "28"),
        "notes": form.get("notes", ""),
        "c1": {
            "name": form.get("c1_name", ""),
            "dob": form.get("c1_dob", ""),
            "ssn_last_4": form.get("c1_ssn_last_4", ""),
            "monthly_salary": form.get("c1_monthly_salary", ""),
        },
        "c2": {
            "name": form.get("c2_name", ""),
            "dob": form.get("c2_dob", ""),
            "ssn_last_4": form.get("c2_ssn_last_4", ""),
            "monthly_salary": form.get("c2_monthly_salary", ""),
        },
        "retirement": rows(
            ["retirement_owner", "retirement_type",
             "retirement_last4", "retirement_label"],
            strip_prefix="retirement_",
        ),
        "non_retirement": rows(
            ["nonret_owner", "nonret_type", "nonret_last4", "nonret_label"],
            strip_prefix="nonret_",
        ),
        "liabilities": rows(
            ["liability_name", "liability_rate", "liability_balance"],
            strip_prefix="liability_",
        ),
        "insurance": rows(
            ["insurance_type", "insurance_deductible"],
            strip_prefix="insurance_",
        ),
        "agreed_monthly_outflow": form.get("agreed_monthly_outflow", ""),
        "private_reserve_target_override": form.get(
            "private_reserve_target_override", ""
        ),
    }


def _values_from_client(client):
    """Extract values from an existing Client into the same shape as _values_from_form."""
    c1 = client.person(PersonRole.CLIENT_1)
    c2 = client.person(PersonRole.CLIENT_2)

    def _person_dict(p):
        if p is None:
            return {"name": "", "dob": "", "ssn_last_4": "", "monthly_salary": ""}
        return {
            "name": p.name or "",
            "dob": p.dob.isoformat() if p.dob else "",
            "ssn_last_4": p.ssn_last_4 or "",
            "monthly_salary": str(p.monthly_salary) if p.monthly_salary is not None else "",
        }

    retirement_rows = [
        {
            "owner": a.owner.value,
            "type": a.type,
            "last4": a.account_number_last_4 or "",
            "label": a.label or "",
        }
        for a in client.accounts
        if a.category == AccountCategory.RETIREMENT
    ]
    nonret_rows = [
        {
            "owner": a.owner.value,
            "type": a.type,
            "last4": a.account_number_last_4 or "",
            "label": a.label or "",
        }
        for a in client.accounts
        if a.category == AccountCategory.NON_RETIREMENT
    ]
    has_trust = any(a.category == AccountCategory.TRUST for a in client.accounts)

    liability_rows = [
        {
            "name": l.name,
            "rate": str(l.interest_rate) if l.interest_rate is not None else "",
            "balance": str(l.balance) if l.balance is not None else "",
        }
        for l in client.liabilities
    ]
    insurance_rows = [
        {
            "type": p.type,
            "deductible": str(p.deductible) if p.deductible is not None else "",
        }
        for p in client.insurance_policies
    ]

    sf = client.static_financials

    return {
        "is_married": client.is_married,
        "has_trust": has_trust,
        "property_address": client.property_address or "",
        "transfer_day_of_month": str(client.transfer_day_of_month),
        "notes": client.notes or "",
        "c1": _person_dict(c1),
        "c2": _person_dict(c2),
        "retirement": retirement_rows,
        "non_retirement": nonret_rows,
        "liabilities": liability_rows,
        "insurance": insurance_rows,
        "agreed_monthly_outflow": (
            str(sf.agreed_monthly_outflow) if sf and sf.agreed_monthly_outflow is not None else ""
        ),
        "private_reserve_target_override": (
            str(sf.private_reserve_target_override)
            if sf and sf.private_reserve_target_override is not None
            else ""
        ),
    }


def _empty_values():
    return {
        "is_married": True,
        "has_trust": False,
        "property_address": "",
        "transfer_day_of_month": "28",
        "notes": "",
        "c1": {"name": "", "dob": "", "ssn_last_4": "", "monthly_salary": ""},
        "c2": {"name": "", "dob": "", "ssn_last_4": "", "monthly_salary": ""},
        "retirement": [],
        "non_retirement": [],
        "liabilities": [],
        "insurance": [],
        "agreed_monthly_outflow": "",
        "private_reserve_target_override": "",
    }


def _form_context(client=None, form_data=None):
    """Context for rendering form.html (create or edit)."""
    if form_data is not None:
        values = _values_from_form(form_data)
    elif client is not None:
        values = _values_from_client(client)
    else:
        values = _empty_values()
    return {
        "client": client,
        "values": values,
        "retirement_types": RETIREMENT_TYPES,
        "non_retirement_types": NON_RETIREMENT_TYPES,
        "insurance_types": INSURANCE_TYPES,
    }


# --- Routes ----------------------------------------------------------------
@clients_bp.route("/", methods=["GET"])
def list_clients():
    clients = Client.query.order_by(Client.id.asc()).all()
    rows = [
        {
            "id": c.id,
            "display_name": _client_display_name(c),
            "is_married": c.is_married,
            "last_report_date": _last_report_date(c),
        }
        for c in clients
    ]
    return render_template("clients/list.html", clients=rows)


@clients_bp.route("/new", methods=["GET"])
def new_client():
    return render_template("clients/form.html", **_form_context(client=None))


@clients_bp.route("/", methods=["POST"])
def create_client():
    data, errors = _parse_client_form(request.form)
    if errors:
        for err in errors:
            flash(err, "error")
        return render_template(
            "clients/form.html",
            **_form_context(client=None, form_data=request.form),
        ), 400

    client = Client()
    db.session.add(client)
    try:
        _apply_to_client(client, data, is_new=True)
        db.session.commit()
    except (ValueError, Exception) as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Could not create client: {exc}", "error")
        return render_template(
            "clients/form.html",
            **_form_context(client=None, form_data=request.form),
        ), 400

    flash("Client created successfully.", "success")
    return redirect(url_for("clients.detail_client", client_id=client.id))


@clients_bp.route("/<int:client_id>", methods=["GET"])
def detail_client(client_id):
    client = Client.query.get(client_id)
    if client is None:
        abort(404)
    retirement = [a for a in client.accounts
                  if a.category == AccountCategory.RETIREMENT]
    non_retirement = [a for a in client.accounts
                      if a.category == AccountCategory.NON_RETIREMENT]
    trust_accounts = [a for a in client.accounts
                      if a.category == AccountCategory.TRUST]
    return render_template(
        "clients/detail.html",
        client=client,
        display_name=_client_display_name(client),
        retirement=retirement,
        non_retirement=non_retirement,
        trust_accounts=trust_accounts,
        PersonRole=PersonRole,
    )


@clients_bp.route("/<int:client_id>/edit", methods=["GET"])
def edit_client(client_id):
    client = Client.query.get(client_id)
    if client is None:
        abort(404)
    return render_template("clients/form.html", **_form_context(client=client))


@clients_bp.route("/<int:client_id>", methods=["POST"])
def update_client(client_id):
    client = Client.query.get(client_id)
    if client is None:
        abort(404)

    data, errors = _parse_client_form(request.form)
    if errors:
        for err in errors:
            flash(err, "error")
        return render_template(
            "clients/form.html",
            **_form_context(client=client, form_data=request.form),
        ), 400

    try:
        _apply_to_client(client, data, is_new=False)
        db.session.commit()
    except (ValueError, Exception) as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Could not update client: {exc}", "error")
        return render_template(
            "clients/form.html",
            **_form_context(client=client, form_data=request.form),
        ), 400

    flash("Client updated successfully.", "success")
    return redirect(url_for("clients.detail_client", client_id=client.id))


@clients_bp.route("/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id):
    client = Client.query.get(client_id)
    if client is None:
        abort(404)
    db.session.delete(client)
    db.session.commit()
    flash("Client deleted.", "success")
    return redirect(url_for("clients.list_clients"))
