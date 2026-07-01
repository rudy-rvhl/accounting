"""Acquisition underwriting — levered IRR / NPV / equity multiple over a hold period.

Models a purchase financed with a Canadian mortgage: equity in (down payment + closing
costs), annual NOI growing at an assumed rate net of debt service, and a sale at exit
priced off an exit cap rate net of selling costs and the remaining mortgage balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from qcre.cfo.finance import irr, npv
from qcre.core.money import Money
from qcre.domain.mortgage import Mortgage


@dataclass
class AcquisitionAssumptions:
    purchase_price: Money
    closing_costs: Money               # transfer duty + legal + inspection
    down_payment_fraction: Decimal     # e.g. 0.25
    mortgage_rate: Decimal             # nominal annual
    amortization_years: int
    year1_noi: Money
    noi_growth: Decimal = Decimal("0.02")
    hold_years: int = 5
    exit_cap_rate: Decimal = Decimal("0.05")
    selling_cost_fraction: Decimal = Decimal("0.04")
    discount_rate: Decimal = Decimal("0.08")


@dataclass(frozen=True)
class UnderwritingResult:
    equity_invested: Money
    loan_amount: Money
    annual_cashflows: list[Money]
    exit_value: Money
    net_sale_proceeds: Money
    irr: Decimal | None
    npv: Money
    equity_multiple: Decimal
    going_in_cap_rate: Decimal


def underwrite(a: AcquisitionAssumptions) -> UnderwritingResult:
    down = (a.purchase_price * a.down_payment_fraction).round(2)
    loan = (a.purchase_price - down).round(2)
    equity = (down + a.closing_costs).round(2)

    mortgage = Mortgage("UW", "UW", loan, a.mortgage_rate, a.amortization_years, date(2026, 1, 1))
    annual_debt_service = (mortgage.payment * 12).round(2)

    cashflows: list[Money] = [(-equity)]
    noi = a.year1_noi
    final_year_noi = noi
    for year in range(1, a.hold_years + 1):
        cf = (noi - annual_debt_service).round(2)
        final_year_noi = noi
        if year == a.hold_years:
            # Exit value off the *forward* NOI (next year's), net of costs & loan payoff.
            forward_noi = (noi * (Decimal(1) + a.noi_growth)).round(2)
            exit_value = (forward_noi / a.exit_cap_rate).round(2)
            balance = mortgage.balance_at(2026 + a.hold_years - 1)
            net_sale = (exit_value * (Decimal(1) - a.selling_cost_fraction) - balance).round(2)
            cf = (cf + net_sale).round(2)
        cashflows.append(cf)
        noi = (noi * (Decimal(1) + a.noi_growth)).round(2)

    forward_noi = (final_year_noi * (Decimal(1) + a.noi_growth)).round(2)
    exit_value = (forward_noi / a.exit_cap_rate).round(2)
    balance = mortgage.balance_at(2026 + a.hold_years - 1)
    net_sale = (exit_value * (Decimal(1) - a.selling_cost_fraction) - balance).round(2)

    project_irr = irr(cashflows)
    project_npv = npv(a.discount_rate, cashflows).round(2)
    total_in = equity
    total_out = sum((cf for cf in cashflows[1:]), Money.zero())
    equity_multiple = (total_out.amount / total_in.amount) if total_in.is_positive() else Decimal(0)

    return UnderwritingResult(
        equity_invested=equity,
        loan_amount=loan,
        annual_cashflows=cashflows,
        exit_value=exit_value,
        net_sale_proceeds=net_sale,
        irr=project_irr,
        npv=project_npv,
        equity_multiple=equity_multiple,
        going_in_cap_rate=(a.year1_noi.amount / a.purchase_price.amount),
    )
