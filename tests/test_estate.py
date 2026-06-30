"""Tests for the estate-freeze and 21-year deemed-disposition planner."""

from datetime import date
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.estate_freeze import EstateFreezePlanner
from qcre.tax.rates import get_ratebook

RB = get_ratebook(2026)


def test_estate_freeze_shifts_growth_and_defers_tax():
    p = EstateFreezePlanner(RB)
    fr = p.freeze(Money("2000000"), Money("1000000"), freeze_date=date(2026, 1, 1),
                  annual_growth=Decimal("0.04"), horizon_years=21)
    # 2,000,000 * 1.04^21 ≈ 4,556,167 → growth shifted ≈ 2,556,167
    assert fr.projected_value_at_horizon > Money("4500000")
    assert fr.growth_shifted_to_trust > Money("2500000")
    # Estate tax deferred = growth * 50% * top rate (53.31%)
    expected = (fr.growth_shifted_to_trust * Decimal("0.5") * RB.personal.top_combined_rate).round(2)
    assert fr.estate_tax_deferred_estimate == expected


def test_deemed_disposition_plan_quantifies_rollout_benefit():
    p = EstateFreezePlanner(RB)
    plan = p.deemed_disposition_plan(
        trust_created=date(2010, 6, 1), current_fmv=Money("1500000"), acb=Money("1000000"),
        as_of=date(2026, 6, 30), annual_growth=Decimal("0.04"))
    assert plan.anniversary == date(2031, 6, 1)
    assert plan.years_remaining == 5
    assert plan.tax_if_rollout.is_zero()          # s.107(2) rollout defers the gain
    assert plan.tax_if_pay.is_positive()
    assert plan.tax_deferred_by_rollout == plan.tax_if_pay
    assert "ROLL OUT" in plan.recommendation
