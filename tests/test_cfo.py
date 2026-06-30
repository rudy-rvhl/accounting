"""Tests for CFO finance helpers and hold-vs-sell analysis."""

from decimal import Decimal

from qcre.cfo.finance import irr, npv
from qcre.cfo.holdvssell import after_tax_sale, hold_vs_sell
from qcre.core.money import Money
from qcre.tax.rates import get_ratebook

RB = get_ratebook(2026)


def test_npv_basic():
    # $100 a year for 3 years at 10% ≈ 248.69
    val = npv(Decimal("0.10"), [Money("0"), Money("100"), Money("100"), Money("100")])
    assert Money("248") < val < Money("249")


def test_irr_recovers_known_rate():
    # -1000 now, +1100 in one year → 10% IRR
    r = irr([Money("-1000"), Money("1100")])
    assert r is not None and abs(r - Decimal("0.10")) < Decimal("0.001")


def test_after_tax_sale_includes_recapture_and_cda():
    res = after_tax_sale(
        sale_price=Money("2500000"), selling_cost_fraction=Decimal("0.04"),
        original_cost=Money("1640000"), acb=Money("1700000"),
        building_ucc=Money("1400000"), mortgage_payoff=Money("1200000"), ratebook=RB,
    )
    # Net proceeds 2.4M > original cost → full recapture of (1.64M - 1.4M) = 240k.
    assert res.recapture == Money("240000.00")
    assert res.cda_addition.is_positive()       # non-taxable half of the capital gain
    assert res.net_after_tax_cash.is_positive()


def test_hold_vs_sell_recommends():
    res = hold_vs_sell(
        sale_price=Money("2500000"), selling_cost_fraction=Decimal("0.04"),
        original_cost=Money("1640000"), acb=Money("1700000"), building_ucc=Money("1400000"),
        mortgage_payoff=Money("1200000"), annual_after_tax_cashflow=Money("60000"),
        hold_years=5, future_sale_price=Money("2900000"), discount_rate=Decimal("0.08"),
        ratebook=RB,
    )
    assert res.recommendation.startswith(("SELL", "HOLD"))
    assert len(res.notes) >= 2
