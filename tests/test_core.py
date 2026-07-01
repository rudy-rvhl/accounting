"""Tests for the money/precision layer and the double-entry ledger."""

from datetime import date
from decimal import Decimal

import pytest

from qcre.core import (
    JournalEntry,
    JournalLine,
    Ledger,
    Money,
    default_chart,
)


# --- Money ------------------------------------------------------------------
def test_money_uses_decimal_not_float():
    assert Money("0.1") + Money("0.2") == Money("0.3")  # would fail with floats
    assert (Money("0.1") + Money("0.2")).round() == Money("0.30")


def test_money_multiplication_and_rounding():
    qst = Money("1000.00") * Decimal("0.09975")
    assert qst.round(2) == Money("99.75")


def test_money_allocate_no_pennies_lost():
    parts = Money("100.00").allocate([1, 1, 1])
    assert sum(parts, Money.zero()) == Money("100.00")
    assert sorted(p.round(2) for p in parts) == [Money("33.33"), Money("33.33"), Money("33.34")]


def test_money_allocate_by_square_footage():
    # 70% commercial / 30% residential floor area
    commercial, residential = Money("1000.00").allocate([Decimal("7000"), Decimal("3000")])
    assert commercial == Money("700.00")
    assert residential == Money("300.00")
    assert commercial + residential == Money("1000.00")


def test_money_format():
    assert Money("1234567.5").format() == "$1,234,567.50"
    assert Money("-1234.5").format() == "-$1,234.50"


# --- Chart of accounts ------------------------------------------------------
def test_default_chart_normal_balances():
    coa = default_chart()
    assert coa.get("1010").is_debit_normal()  # bank = asset = debit
    assert not coa.get("4000").is_debit_normal()  # revenue = credit
    assert coa.get("1510").normal_balance == "credit"  # accumulated amort = contra-asset


def test_tags_locate_accounts():
    coa = default_chart()
    rent_accounts = {a.code for a in coa.by_tag("rent")}
    assert {"4000", "4010"}.issubset(rent_accounts)


# --- Journal entries --------------------------------------------------------
def test_unbalanced_entry_rejected():
    with pytest.raises(ValueError, match="out of balance"):
        JournalEntry(
            date=date(2026, 1, 1),
            description="bad",
            lines=[
                JournalLine("1010", debit=Money("100")),
                JournalLine("4000", credit=Money("90")),
            ],
        )


def test_line_cannot_have_both_debit_and_credit():
    with pytest.raises(ValueError):
        JournalLine("1010", debit=Money("10"), credit=Money("10"))


# --- Ledger -----------------------------------------------------------------
def test_ledger_posts_and_reports_balances():
    ledger = Ledger(default_chart())
    ledger.post(
        JournalEntry(
            date=date(2026, 1, 1),
            description="Receive residential rent",
            lines=[
                JournalLine("1010", debit=Money("2000")),
                JournalLine("4000", credit=Money("2000")),
            ],
        )
    )
    assert ledger.balance("1010") == Money("2000.00")
    assert ledger.balance("4000") == Money("2000.00")  # natural (credit) balance positive
    assert ledger.is_in_balance()


def test_ledger_rejects_unknown_account():
    ledger = Ledger(default_chart())
    with pytest.raises(KeyError):
        ledger.post(
            JournalEntry(
                date=date(2026, 1, 1),
                description="bad",
                lines=[
                    JournalLine("9999", debit=Money("1")),
                    JournalLine("1010", credit=Money("1")),
                ],
            )
        )


def test_property_dimension_filtering():
    ledger = Ledger(default_chart())
    for prop, rent in [("A", "1000"), ("B", "1500")]:
        ledger.post(
            JournalEntry(
                date=date(2026, 1, 1),
                description="rent",
                property_id=prop,
                lines=[
                    JournalLine("1010", debit=Money(rent)),
                    JournalLine("4000", credit=Money(rent)),
                ],
            )
        )
    assert ledger.balance("4000", property_id="A") == Money("1000.00")
    assert ledger.balance("4000", property_id="B") == Money("1500.00")
    assert ledger.balance("4000") == Money("2500.00")
