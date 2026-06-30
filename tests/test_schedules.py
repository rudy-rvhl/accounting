"""Tests for T2 / CO-17 schedule mapping — figures must reconcile to the engine."""

from qcre.analysis import tax_position
from qcre.core.money import Money
from qcre.reports.tax_schedules import build_tax_schedules
from qcre.sample import build_sample_company


def _line(sched, ref=None, contains=None):
    for ln in sched.lines:
        if ref and ln.ref == ref:
            return ln
        if contains and contains.lower() in ln.label.lower():
            return ln
    raise AssertionError(f"line not found: {ref or contains}")


def test_schedule1_net_income_for_tax_reconciles():
    co = build_sample_company()
    pos = tax_position(co)
    scheds = build_tax_schedules(co)
    s1 = next(s for s in scheds if "Schedule 1" in s.name)
    net_for_tax = _line(s1, ref="L300").amount
    # Schedule 1 must arrive at the same taxable rental income as the tax engine.
    assert net_for_tax == pos.taxable_rental_income


def test_federal_plus_quebec_equals_total_corporate_tax():
    co = build_sample_company()
    pos = tax_position(co)
    scheds = build_tax_schedules(co)
    fed = _line(next(s for s in scheds if s.name.startswith("T2 —")),
                contains="Federal tax payable").amount
    qc = _line(next(s for s in scheds if s.form.startswith("CO-17")),
               contains="Québec tax payable").amount
    assert (fed + qc).round(2) == pos.corporate.total_tax


def test_schedule8_cca_total_matches():
    co = build_sample_company()
    pos = tax_position(co)
    scheds = build_tax_schedules(co)
    s8 = next(s for s in scheds if "Schedule 8" in s.name)
    total = _line(s8, ref="Total").amount
    assert total == pos.cca_claimed
