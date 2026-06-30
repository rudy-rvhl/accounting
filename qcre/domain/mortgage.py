"""Mortgage amortization with Canadian semi-annual compounding.

By law, Canadian fixed-rate mortgage interest is compounded **semi-annually, not in
advance** — so the effective monthly rate is derived from a semi-annual rate, not by
dividing the annual rate by 12. Getting this right matters for the interest/principal
split that feeds both the income statement (interest is deductible; principal is not) and
debt-service coverage ratios.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from qcre.core.money import Money


@dataclass(frozen=True)
class AmortizationRow:
    period: int
    payment_date: date
    payment: Money
    interest: Money
    principal: Money
    balance: Money


@dataclass
class Mortgage:
    mortgage_id: str
    property_id: str
    principal: Money
    annual_rate: Decimal              # nominal annual rate, e.g. Decimal("0.0525")
    amortization_years: int
    start_date: date
    payments_per_year: int = 12
    compounding_per_year: int = 2     # Canadian fixed mortgages: semi-annual

    @property
    def periodic_rate(self) -> Decimal:
        """Effective rate per payment period from semi-annual compounding."""
        semi = self.annual_rate / self.compounding_per_year
        exponent = Decimal(self.compounding_per_year) / Decimal(self.payments_per_year)
        # (1 + semi)^(compounding/payments) - 1
        base = Decimal(1) + semi
        return base ** exponent - Decimal(1)

    @property
    def n_payments(self) -> int:
        return self.amortization_years * self.payments_per_year

    @property
    def payment(self) -> Money:
        i = self.periodic_rate
        n = self.n_payments
        if i == 0:
            return (self.principal / n).round(2)
        factor = (Decimal(1) - (Decimal(1) + i) ** (-n))
        return (self.principal * i / factor).round(2)

    def schedule(self, periods: int | None = None) -> list[AmortizationRow]:
        i = self.periodic_rate
        pmt = self.payment
        balance = self.principal
        rows: list[AmortizationRow] = []
        count = periods or self.n_payments
        months_step = max(1, 12 // self.payments_per_year)
        for p in range(1, count + 1):
            interest = (balance * i).round(2)
            principal = (pmt - interest).round(2)
            # Final payment clears the balance exactly (absorbs accumulated rounding).
            if principal >= balance or balance <= pmt:
                principal = balance.round(2)
                pmt_actual = (principal + interest).round(2)
            else:
                pmt_actual = pmt
            balance = (balance - principal).round(2)
            month = self.start_date.month - 1 + p * months_step
            year = self.start_date.year + month // 12
            pay_date = date(year, month % 12 + 1, 1)
            rows.append(AmortizationRow(p, pay_date, pmt_actual, interest, principal, balance))
            if balance.is_zero():
                break
        return rows

    def year_split(self, year: int) -> tuple[Money, Money]:
        """(interest, principal) paid during calendar *year* — interest is deductible."""
        interest = Money.zero()
        principal = Money.zero()
        for row in self.schedule():
            if row.payment_date.year == year:
                interest += row.interest
                principal += row.principal
            elif row.payment_date.year > year:
                break
        return interest.round(2), principal.round(2)

    def balance_at(self, year: int) -> Money:
        bal = self.principal
        for row in self.schedule():
            bal = row.balance
            if row.payment_date.year > year:
                break
        return bal.round(2)
