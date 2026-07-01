"""Personal income tax (Quebec resident) — used for integration analysis.

This module supports the salary-vs-dividend and distribute-vs-retain decisions and the
TOSI overlay. It computes combined federal + Quebec tax on ordinary income and on
eligible / non-eligible dividends, applying the dividend gross-up and tax credits and the
**16.5% Quebec abatement** (a reduction of basic federal tax unique to Quebec residents).

It is a planning **estimate**: it applies the basic personal amount but ignores QPP/EI
contributions, the Quebec health/other contributions, and most other credits. Use it for
relative comparisons, not as a personal tax return.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.rates import RateBook, get_ratebook


@dataclass(frozen=True)
class PersonalTaxResult:
    ordinary_income: Money
    eligible_dividends: Money
    non_eligible_dividends: Money
    taxable_income: Money         # after gross-up
    federal_tax: Money            # after abatement
    quebec_tax: Money
    total_tax: Money

    @property
    def after_tax(self) -> Money:
        cash = self.ordinary_income + self.eligible_dividends + self.non_eligible_dividends
        return (cash - self.total_tax).round(2)

    @property
    def average_rate(self) -> Decimal:
        cash = self.ordinary_income + self.eligible_dividends + self.non_eligible_dividends
        return (self.total_tax.amount / cash.amount) if cash.is_positive() else Decimal(0)


class PersonalTaxEngine:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()

    def marginal_rate_ordinary(self, income: Money) -> Decimal:
        p = self.rb.personal
        fed = p.federal.marginal_rate(income) * (Decimal(1) - p.quebec_abatement)
        return fed + p.quebec.marginal_rate(income)

    def compute(
        self,
        ordinary_income: Money = Money.zero(),
        *,
        eligible_dividends: Money = Money.zero(),
        non_eligible_dividends: Money = Money.zero(),
    ) -> PersonalTaxResult:
        p = self.rb.personal
        d = self.rb.dividends

        gu_elig = (eligible_dividends * (Decimal(1) + d.eligible_gross_up))
        gu_nonelig = (non_eligible_dividends * (Decimal(1) + d.non_eligible_gross_up))
        taxable = (ordinary_income + gu_elig + gu_nonelig).round(2)

        # Federal
        fed_before = p.federal.tax_on(taxable)
        fed_credits = (
            p.federal_bpa * p.federal_lowest_rate
            + gu_elig * d.federal_dtc_eligible
            + gu_nonelig * d.federal_dtc_non_eligible
        )
        basic_federal = max(Money.zero(), fed_before - fed_credits, key=lambda m: m.amount)
        net_federal = (basic_federal * (Decimal(1) - p.quebec_abatement)).round(2)

        # Quebec
        qc_before = p.quebec.tax_on(taxable)
        qc_credits = (
            p.quebec_bpa * p.quebec_lowest_rate
            + gu_elig * d.quebec_dtc_eligible
            + gu_nonelig * d.quebec_dtc_non_eligible
        )
        qc_tax = max(Money.zero(), qc_before - qc_credits, key=lambda m: m.amount).round(2)

        return PersonalTaxResult(
            ordinary_income=ordinary_income.round(2),
            eligible_dividends=eligible_dividends.round(2),
            non_eligible_dividends=non_eligible_dividends.round(2),
            taxable_income=taxable,
            federal_tax=net_federal,
            quebec_tax=qc_tax,
            total_tax=(net_federal + qc_tax).round(2),
        )
