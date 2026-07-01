"""After-tax hold-vs-sell analysis for a corporately-held property.

Selling triggers two tax events inside the corporation: **CCA recapture** (ordinary
investment income) and a **capital gain** (50% taxable). The non-taxable half of the gain
lands in the Capital Dividend Account and can be paid out to shareholders tax-free — a
real part of the after-tax return. This module nets all of that into the cash a sale
actually puts in the owner's hands today, and compares it to the present value of holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qcre.cfo.finance import npv
from qcre.core.money import Money
from qcre.tax.capital import CapitalGainsEngine
from qcre.tax.rates import RateBook, get_ratebook


@dataclass(frozen=True)
class SaleTaxResult:
    gross_proceeds: Money
    selling_costs: Money
    mortgage_payoff: Money
    recapture: Money
    taxable_capital_gain: Money
    corporate_tax: Money
    cda_addition: Money
    net_after_tax_cash: Money


@dataclass(frozen=True)
class HoldVsSellResult:
    sell_now: SaleTaxResult
    hold_pv_equity: Money
    recommendation: str
    notes: list[str]


def after_tax_sale(
    *,
    sale_price: Money,
    selling_cost_fraction: Decimal,
    original_cost: Money,
    acb: Money,
    building_ucc: Money,
    mortgage_payoff: Money,
    ratebook: RateBook | None = None,
) -> SaleTaxResult:
    rb = ratebook or get_ratebook()
    c = rb.corporate
    cg = CapitalGainsEngine(rb)

    selling_costs = (sale_price * selling_cost_fraction).round(2)
    net_proceeds = (sale_price - selling_costs).round(2)

    # Recapture: building proceeds (capped at original cost) less UCC, taxed as investment income.
    building_proceeds_for_recapture = min(net_proceeds, original_cost, key=lambda m: m.amount)
    recapture = max(Money.zero(), building_proceeds_for_recapture - building_ucc, key=lambda m: m.amount).round(2)

    gain = cg.on_disposition(proceeds=net_proceeds, acb=acb)
    tax_on_recapture = (recapture * c.combined_investment).round(2)
    tax_on_gain = (gain.taxable_capital_gain * c.combined_investment).round(2)
    corporate_tax = (tax_on_recapture + tax_on_gain).round(2)

    net_cash = (net_proceeds - mortgage_payoff - corporate_tax).round(2)
    return SaleTaxResult(
        gross_proceeds=sale_price.round(2),
        selling_costs=selling_costs,
        mortgage_payoff=mortgage_payoff.round(2),
        recapture=recapture,
        taxable_capital_gain=gain.taxable_capital_gain,
        corporate_tax=corporate_tax,
        cda_addition=gain.cda_addition,
        net_after_tax_cash=net_cash,
    )


def hold_vs_sell(
    *,
    sale_price: Money,
    selling_cost_fraction: Decimal,
    original_cost: Money,
    acb: Money,
    building_ucc: Money,
    mortgage_payoff: Money,
    annual_after_tax_cashflow: Money,
    hold_years: int,
    future_sale_price: Money,
    discount_rate: Decimal,
    ratebook: RateBook | None = None,
) -> HoldVsSellResult:
    rb = ratebook or get_ratebook()
    sell_now = after_tax_sale(
        sale_price=sale_price, selling_cost_fraction=selling_cost_fraction,
        original_cost=original_cost, acb=acb, building_ucc=building_ucc,
        mortgage_payoff=mortgage_payoff, ratebook=rb,
    )

    # Hold: PV of annual after-tax cash flows plus the after-tax proceeds at the horizon.
    future_sale = after_tax_sale(
        sale_price=future_sale_price, selling_cost_fraction=selling_cost_fraction,
        original_cost=original_cost, acb=acb, building_ucc=building_ucc,
        mortgage_payoff=mortgage_payoff, ratebook=rb,
    )
    flows = [Money.zero()] + [annual_after_tax_cashflow] * hold_years
    flows[-1] = (flows[-1] + future_sale.net_after_tax_cash).round(2)
    hold_pv = npv(discount_rate, flows).round(2)

    notes = [
        f"Selling now releases {sell_now.cda_addition.format()} to the Capital Dividend "
        f"Account — payable to shareholders tax-free.",
        f"Recapture of {sell_now.recapture.format()} is taxed as investment income "
        f"(≈{rb.corporate.combined_investment*100:.2f}%); the capital gain is 50% taxable.",
    ]
    if sell_now.net_after_tax_cash >= hold_pv:
        rec = "SELL — after-tax cash from selling now exceeds the present value of holding."
    else:
        rec = "HOLD — present value of holding exceeds the after-tax cash from selling now."
    return HoldVsSellResult(sell_now, hold_pv, rec, notes)
