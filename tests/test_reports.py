"""Integration tests: statements and CFO analytics over the sample company."""

from decimal import Decimal

import pytest

from qcre.cfo.advisory import Severity, build_advisory
from qcre.cfo.kpis import PropertyKPIs
from qcre.cfo.underwriting import AcquisitionAssumptions, underwrite
from qcre.core.money import Money
from qcre.reports.framework import Framework
from qcre.reports.statements import FinancialStatements
from qcre.sample import build_sample_company
from qcre.tax.corporate import CorporateIncome, CorporateProfile, CorporateTaxEngine
from qcre.tax.rates import get_ratebook

RB = get_ratebook(2026)


def _line(statement, label_contains):
    for ln in statement.lines:
        if label_contains.lower() in ln.label.lower():
            return ln
    raise AssertionError(f"No line containing {label_contains!r}")


def test_sample_company_books_balance():
    co = build_sample_company()
    assert co.ledger.is_in_balance()


def test_balance_sheet_balances():
    co = build_sample_company()
    fs = FinancialStatements(co.ledger, co.fiscal_year, entity_name=co.entity_name)
    bs = fs.balance_sheet()
    total_assets = _line(bs, "TOTAL ASSETS").amount
    total_le = _line(bs, "TOTAL LIABILITIES & EQUITY").amount
    assert total_assets == total_le
    assert total_assets.is_positive()


def test_income_statement_has_positive_noi():
    co = build_sample_company()
    fs = FinancialStatements(co.ledger, co.fiscal_year, entity_name=co.entity_name)
    income = fs.income_statement()
    noi = _line(income, "Net operating income").amount
    assert noi.is_positive()
    # NOI should exceed net income (interest + amortization + tax sit below it).
    net_income = _line(income, "Net income").amount
    assert noi > net_income


def test_cash_flow_ties_to_ledger():
    co = build_sample_company()
    fs = FinancialStatements(co.ledger, co.fiscal_year, entity_name=co.entity_name)
    cf = fs.cash_flow()
    net_change = _line(cf, "Net change in cash").amount
    check = _line(cf, "per ledger").amount
    assert net_change == check


def test_ifrs_toggle_changes_presentation():
    co = build_sample_company(framework=Framework.IFRS)
    fs = FinancialStatements(
        co.ledger, co.fiscal_year, entity_name=co.entity_name,
        framework=Framework.IFRS, fair_value_adjustment=Money("250000"),
    )
    bs = fs.balance_sheet()
    # Under IFRS the buildings line is shown at fair value (IAS 40).
    assert any("fair value" in ln.label.lower() for ln in bs.lines)


def test_kpis_compute_reasonable_ratios():
    kpis = PropertyKPIs(
        noi=Money("200000"), market_value=Money("4200000"),
        annual_debt_service=Money("178000"), loan_balance=Money("2520000"),
        equity_invested=Money("1700000"), gross_potential_rent=Money("362400"),
        operating_expenses=Money("160000"), effective_gross_income=Money("360000"),
    )
    assert Decimal("0.04") < kpis.cap_rate < Decimal("0.06")
    assert Decimal("1.0") < kpis.dscr < Decimal("1.3")
    assert kpis.ltv == Decimal("0.6")
    assert kpis.pre_tax_cash_flow == Money("22000.00")


def test_underwriting_produces_irr():
    res = underwrite(AcquisitionAssumptions(
        purchase_price=Money("2000000"), closing_costs=Money("60000"),
        down_payment_fraction=Decimal("0.30"), mortgage_rate=Decimal("0.05"),
        amortization_years=25, year1_noi=Money("100000"),
        noi_growth=Decimal("0.025"), hold_years=5, exit_cap_rate=Decimal("0.045"),
    ))
    assert res.irr is not None
    assert res.equity_invested == Money("660000.00")
    assert len(res.annual_cashflows) == 6  # year 0 outlay + 5 years


def test_advisory_flags_sib_and_tosi():
    co = build_sample_company()
    eng = CorporateTaxEngine(RB)
    corp = eng.compute(
        CorporateIncome(rental_income=Money("150000")),
        CorporateProfile(full_time_employees=co.full_time_employees),
    )
    items = build_advisory(corporate=corp, rental_income=Money("150000"), ratebook=RB)
    assert any("specified investment business" in i.title.lower() for i in items)
    assert any(i.severity == Severity.WARNING for i in items)
