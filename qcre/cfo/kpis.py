"""Real-estate KPIs for CFO oversight.

Computes the metrics lenders and investors actually underwrite to: capitalization rate,
cash-on-cash return, debt-service coverage ratio (DSCR), loan-to-value (LTV), gross rent
multiplier (GRM), operating-expense ratio, and break-even occupancy. All are derived from
NOI, debt service, and value inputs that the ledger and domain models supply.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qcre.core.money import Money


@dataclass(frozen=True)
class PropertyKPIs:
    noi: Money
    market_value: Money
    annual_debt_service: Money
    loan_balance: Money
    equity_invested: Money
    gross_potential_rent: Money
    operating_expenses: Money
    effective_gross_income: Money

    @property
    def cap_rate(self) -> Decimal:
        return self.noi.amount / self.market_value.amount if self.market_value.is_positive() else Decimal(0)

    @property
    def pre_tax_cash_flow(self) -> Money:
        return (self.noi - self.annual_debt_service).round(2)

    @property
    def cash_on_cash(self) -> Decimal:
        return (self.pre_tax_cash_flow.amount / self.equity_invested.amount
                if self.equity_invested.is_positive() else Decimal(0))

    @property
    def dscr(self) -> Decimal:
        return (self.noi.amount / self.annual_debt_service.amount
                if self.annual_debt_service.is_positive() else Decimal(0))

    @property
    def ltv(self) -> Decimal:
        return self.loan_balance.amount / self.market_value.amount if self.market_value.is_positive() else Decimal(0)

    @property
    def grm(self) -> Decimal:
        return (self.market_value.amount / self.gross_potential_rent.amount
                if self.gross_potential_rent.is_positive() else Decimal(0))

    @property
    def operating_expense_ratio(self) -> Decimal:
        return (self.operating_expenses.amount / self.effective_gross_income.amount
                if self.effective_gross_income.is_positive() else Decimal(0))

    @property
    def break_even_occupancy(self) -> Decimal:
        if self.gross_potential_rent.is_zero():
            return Decimal(0)
        return (self.operating_expenses + self.annual_debt_service).amount / self.gross_potential_rent.amount

    @property
    def vacancy_rate(self) -> Decimal:
        if self.gross_potential_rent.is_zero():
            return Decimal(0)
        return ((self.gross_potential_rent - self.effective_gross_income).amount
                / self.gross_potential_rent.amount)

    def as_dict(self) -> dict[str, str]:
        pct = lambda d: f"{d * 100:.2f}%"
        return {
            "NOI": self.noi.format(),
            "Market value": self.market_value.format(),
            "Cap rate": pct(self.cap_rate),
            "Pre-tax cash flow": self.pre_tax_cash_flow.format(),
            "Cash-on-cash return": pct(self.cash_on_cash),
            "DSCR": f"{self.dscr:.2f}x",
            "LTV": pct(self.ltv),
            "GRM": f"{self.grm:.1f}",
            "Operating expense ratio": pct(self.operating_expense_ratio),
            "Break-even occupancy": pct(self.break_even_occupancy),
            "Vacancy rate": pct(self.vacancy_rate),
        }


def portfolio_kpis(properties: list[PropertyKPIs]) -> PropertyKPIs:
    """Aggregate a list of per-property KPIs into a single portfolio view."""
    z = Money.zero
    agg = PropertyKPIs(
        noi=sum((p.noi for p in properties), z()),
        market_value=sum((p.market_value for p in properties), z()),
        annual_debt_service=sum((p.annual_debt_service for p in properties), z()),
        loan_balance=sum((p.loan_balance for p in properties), z()),
        equity_invested=sum((p.equity_invested for p in properties), z()),
        gross_potential_rent=sum((p.gross_potential_rent for p in properties), z()),
        operating_expenses=sum((p.operating_expenses for p in properties), z()),
        effective_gross_income=sum((p.effective_gross_income for p in properties), z()),
    )
    return agg
