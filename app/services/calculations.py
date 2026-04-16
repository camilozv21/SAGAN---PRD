"""Pure-Python implementation of SACS and TCC business rules.

These functions are the single source of truth for the financial math
used in PDFs and by the live-preview panel (mirrored in JS). Keep them
side-effect free and in Decimal so the same numbers flow through every
surface: form panel, persistence, and PDFs.

PRD rules reflected here:
- Inflow = salary(client_1) + salary(client_2)
- Excess = inflow - outflow (may be negative)
- Private reserve target = 6 * outflow + sum(insurance deductibles)
- C1/C2 retirement totals sum only their respective retirement accounts
- Non-retirement total NEVER includes the trust (Rebecca 24:28)
- Grand total = C1 retirement + C2 retirement + non-retirement + trust
- Liabilities are tracked separately and NEVER subtracted (Rebecca 26:15)
"""
from decimal import Decimal
from typing import Iterable, Optional

Number = Optional[Decimal | int | float | str]


def _d(value: Number) -> Decimal:
    """Coerce input to Decimal. ``None`` and empty strings become 0."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip()
    if raw == "":
        return Decimal("0")
    return Decimal(raw)


def _sum(values: Iterable[Number]) -> Decimal:
    total = Decimal("0")
    for v in values:
        total += _d(v)
    return total


def calculate_inflow(salary_c1: Number, salary_c2: Number) -> Decimal:
    """Monthly inflow = salary(C1) + salary(C2). Single household: pass 0 for C2."""
    return _d(salary_c1) + _d(salary_c2)


def calculate_excess(inflow: Number, outflow: Number) -> Decimal:
    """Inflow - outflow. May be negative (displayed as-is)."""
    return _d(inflow) - _d(outflow)


def calculate_target(outflow: Number, deductibles: Iterable[Number]) -> Decimal:
    """Private reserve target = 6 * outflow + sum(insurance deductibles)."""
    return _d(outflow) * Decimal("6") + _sum(deductibles)


def calculate_c1_retirement(balances: Iterable[Number]) -> Decimal:
    """Sum of Client 1 retirement account balances."""
    return _sum(balances)


def calculate_c2_retirement(balances: Iterable[Number]) -> Decimal:
    """Sum of Client 2 retirement account balances."""
    return _sum(balances)


def calculate_non_retirement_total(balances: Iterable[Number]) -> Decimal:
    """Sum of non-retirement balances. Callers MUST exclude the trust."""
    return _sum(balances)


def calculate_grand_total(
    c1_retirement: Number,
    c2_retirement: Number,
    non_retirement: Number,
    trust: Number,
) -> Decimal:
    """Grand total net worth. Liabilities never enter this sum."""
    return _d(c1_retirement) + _d(c2_retirement) + _d(non_retirement) + _d(trust)


def calculate_liabilities_total(balances: Iterable[Number]) -> Decimal:
    """Sum of liabilities. Shown in its own box — never subtracted."""
    return _sum(balances)
