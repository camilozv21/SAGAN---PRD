"""Unit tests for SACS / TCC calculation rules.

Each PRD rule is locked in with a dedicated test so a future change that
breaks a business invariant (e.g. accidentally subtracting liabilities)
will fail loudly.
"""
import inspect
from decimal import Decimal

from app.services import calculations
from app.services.calculations import (
    calculate_c1_retirement,
    calculate_c2_retirement,
    calculate_excess,
    calculate_grand_total,
    calculate_inflow,
    calculate_liabilities_total,
    calculate_non_retirement_total,
    calculate_target,
)


# --- Inflow -----------------------------------------------------------------
def test_inflow_both_spouses():
    assert calculate_inflow(Decimal("8000"), Decimal("5000")) == Decimal("13000")


def test_inflow_single_household():
    # Single household: caller passes 0 for the missing spouse.
    assert calculate_inflow(Decimal("8000"), Decimal("0")) == Decimal("8000")


def test_inflow_none_is_zero():
    assert calculate_inflow(None, Decimal("5000")) == Decimal("5000")


def test_inflow_accepts_numeric_strings():
    assert calculate_inflow("8000.50", "1500.25") == Decimal("9500.75")


# --- Excess -----------------------------------------------------------------
def test_excess_positive():
    assert calculate_excess(Decimal("13000"), Decimal("10000")) == Decimal("3000")


def test_excess_negative_allowed():
    # Outflow > inflow: excess is negative (display as-is, no clamp).
    assert calculate_excess(Decimal("10000"), Decimal("12000")) == Decimal("-2000")


def test_excess_zero():
    assert calculate_excess(Decimal("10000"), Decimal("10000")) == Decimal("0")


# --- Target (private reserve) ----------------------------------------------
def test_target_six_times_outflow_plus_deductibles():
    # 6 * 10000 + (2500 + 1000) = 63500
    deductibles = [Decimal("2500"), Decimal("1000")]
    assert calculate_target(Decimal("10000"), deductibles) == Decimal("63500")


def test_target_no_deductibles():
    assert calculate_target(Decimal("10000"), []) == Decimal("60000")


def test_target_zero_outflow():
    assert calculate_target(Decimal("0"), [Decimal("500")]) == Decimal("500")


# --- Retirement totals ------------------------------------------------------
def test_c1_retirement_sum():
    assert calculate_c1_retirement(
        [Decimal("100000"), Decimal("250000"), Decimal("50000")]
    ) == Decimal("400000")


def test_c1_retirement_empty():
    assert calculate_c1_retirement([]) == Decimal("0")


def test_c2_retirement_sum():
    assert calculate_c2_retirement(
        [Decimal("75000"), Decimal("120000")]
    ) == Decimal("195000")


def test_c2_retirement_empty_for_single_household():
    # A single household has no C2 retirement accounts.
    assert calculate_c2_retirement([]) == Decimal("0")


# --- Non-retirement total ---------------------------------------------------
def test_non_retirement_sum():
    assert calculate_non_retirement_total(
        [Decimal("10000"), Decimal("25000"), Decimal("5000")]
    ) == Decimal("40000")


def test_non_retirement_empty():
    assert calculate_non_retirement_total([]) == Decimal("0")


# --- Grand total ------------------------------------------------------------
def test_grand_total_four_components():
    total = calculate_grand_total(
        c1_retirement=Decimal("400000"),
        c2_retirement=Decimal("195000"),
        non_retirement=Decimal("40000"),
        trust=Decimal("850000"),
    )
    assert total == Decimal("1485000")


def test_grand_total_no_trust():
    total = calculate_grand_total(
        c1_retirement=Decimal("100000"),
        c2_retirement=Decimal("0"),
        non_retirement=Decimal("35000"),
        trust=Decimal("0"),
    )
    assert total == Decimal("135000")


def test_grand_total_single_household_no_c2():
    total = calculate_grand_total(
        c1_retirement=Decimal("500000"),
        c2_retirement=Decimal("0"),
        non_retirement=Decimal("80000"),
        trust=Decimal("600000"),
    )
    assert total == Decimal("1180000")


# --- Liabilities ------------------------------------------------------------
def test_liabilities_total():
    assert calculate_liabilities_total(
        [Decimal("224218.24"), Decimal("11152.00")]
    ) == Decimal("235370.24")


def test_liabilities_empty():
    assert calculate_liabilities_total([]) == Decimal("0")


# --- PRD invariants ---------------------------------------------------------
def test_liabilities_never_subtracted_from_grand_total():
    """PRD: 'we do not subtract liabilities from their net worth' (Rebecca 26:15)."""
    sig = inspect.signature(calculate_grand_total)
    assert not any("liabilit" in name.lower() for name in sig.parameters)

    grand = calculate_grand_total(
        c1_retirement=Decimal("100000"),
        c2_retirement=Decimal("100000"),
        non_retirement=Decimal("50000"),
        trust=Decimal("500000"),
    )
    liabilities = calculate_liabilities_total([Decimal("300000")])
    # The net worth is independent of liabilities.
    assert grand == Decimal("750000")
    assert liabilities == Decimal("300000")


def test_trust_never_added_to_non_retirement_total():
    """PRD: 'we do not add the trust in [to non-retirement total]' (Rebecca 24:28)."""
    non_retirement = [Decimal("10000"), Decimal("25000")]
    trust = Decimal("600000")
    total = calculate_non_retirement_total(non_retirement)
    assert total == Decimal("35000")
    # If trust had leaked in, it would equal 635000.
    assert total != total + trust


def test_calculations_module_is_side_effect_free():
    """No I/O / DB imports in the calculations module — it must be pure."""
    source = inspect.getsource(calculations)
    for forbidden in ("from app import db", "sqlalchemy", "flask"):
        assert forbidden not in source, f"calculations.py must not import {forbidden}"
