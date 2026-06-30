"""Tax-optimization analyses for the owner-manager of a Quebec real-estate CCPC.

These are *planning estimates* built on the dated rate book; they compare alternatives at
the margin and surface the trade-offs. They are not a substitute for a CPA's advice.

Included:
* :meth:`Optimizer.salary_vs_dividend` — net cash to the owner from extracting corporate
  funds as salary (deductible, ordinary personal rates) vs as a dividend (paid from
  after-tax corporate income, taxed with the dividend tax credit).
* :meth:`Optimizer.cost_of_specified_investment_business` — how much the ~50.17%
  investment rate on rental income costs versus the small-business rate, to frame the
  ">5 full-time employees" / active-business decision.
* :meth:`Optimizer.corporate_instalments` — required instalment schedule from prior-year
  tax.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.personal import PersonalTaxEngine
from qcre.tax.rates import RateBook, get_ratebook


@dataclass(frozen=True)
class RemunerationComparison:
    pre_tax_corporate: Money
    # Salary route
    salary_personal_tax: Money
    salary_net_to_owner: Money
    # Dividend route
    corporate_tax_on_income: Money
    dividend_paid: Money
    dividend_personal_tax: Money
    dividend_refund_recovered: Money
    dividend_net_to_owner: Money
    # Verdict
    preferred: str
    advantage: Money
    notes: list[str]


@dataclass(frozen=True)
class SIBCostComparison:
    rental_income: Money
    tax_as_investment: Money
    tax_as_small_business: Money
    annual_difference: Money
    note: str


class Optimizer:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()
        self.personal = PersonalTaxEngine(self.rb)

    # -- salary vs dividend --------------------------------------------------
    def salary_vs_dividend(
        self,
        pre_tax_corporate: Money,
        *,
        income_is_investment: bool = True,
        other_personal_income: Money = Money.zero(),
    ) -> RemunerationComparison:
        """Compare extracting *pre_tax_corporate* dollars of corporate income as salary
        vs as a dividend, for an owner already earning *other_personal_income*.

        Salary is deductible (the corporation pays no tax on it). A dividend is paid from
        after-tax corporate income; for investment income the corporation recovers part of
        its tax through the RDTOH dividend refund when the dividend is paid (modelled).
        Dividends from investment income / SBD income are **non-eligible**.
        """
        c = self.rb.corporate
        notes: list[str] = []

        # --- Salary route: fully deductible at the corporate level. ---
        sal_base = self.personal.compute(ordinary_income=other_personal_income)
        sal_with = self.personal.compute(ordinary_income=other_personal_income + pre_tax_corporate)
        salary_tax = (sal_with.total_tax - sal_base.total_tax).round(2)
        salary_net = (pre_tax_corporate - salary_tax).round(2)
        notes.append(
            "Salary is deductible to the corporation (no corporate tax) but is subject to "
            "personal rates and payroll contributions (QPP/QPIP, ignored here)."
        )

        # --- Dividend route ---
        corp_rate = c.combined_investment if income_is_investment else c.combined_general
        corp_tax = (pre_tax_corporate * corp_rate).round(2)
        after_tax_cash = (pre_tax_corporate - corp_tax).round(2)

        # Investment income generates RDTOH; paying a dividend recovers 38.33% of it.
        refund = Money.zero()
        dividend = after_tax_cash
        if income_is_investment:
            rdtoh = (pre_tax_corporate * c.rdtoh_refundable_rate).round(2)
            # Solve for the dividend that, with its refund, distributes all available cash:
            # dividend = after_tax_cash + min(refund_rate*dividend, rdtoh)
            # Assume RDTOH not binding (typical): dividend = after_tax_cash/(1-refund_rate)
            dividend = (after_tax_cash / (Decimal(1) - c.dividend_refund_rate)).round(2)
            refund = (dividend * c.dividend_refund_rate).round(2)
            if refund > rdtoh:
                refund = rdtoh
                dividend = (after_tax_cash + refund).round(2)
            notes.append(
                f"Investment income: corporation recovers {c.dividend_refund_rate*100:.2f}% of "
                f"the taxable dividend from RDTOH (≈{refund.format()} refund modelled)."
            )

        div_base = self.personal.compute(ordinary_income=other_personal_income)
        div_with = self.personal.compute(
            ordinary_income=other_personal_income, non_eligible_dividends=dividend
        )
        dividend_tax = (div_with.total_tax - div_base.total_tax).round(2)
        dividend_net = (dividend - dividend_tax).round(2)

        if salary_net >= dividend_net:
            preferred, advantage = "salary", (salary_net - dividend_net).round(2)
        else:
            preferred, advantage = "dividend", (dividend_net - salary_net).round(2)

        return RemunerationComparison(
            pre_tax_corporate=pre_tax_corporate.round(2),
            salary_personal_tax=salary_tax,
            salary_net_to_owner=salary_net,
            corporate_tax_on_income=corp_tax,
            dividend_paid=dividend,
            dividend_personal_tax=dividend_tax,
            dividend_refund_recovered=refund,
            dividend_net_to_owner=dividend_net,
            preferred=preferred,
            advantage=advantage,
            notes=notes,
        )

    # -- cost of the specified-investment-business characterization ----------
    def cost_of_specified_investment_business(self, rental_income: Money) -> SIBCostComparison:
        c = self.rb.corporate
        as_investment = (rental_income * c.combined_investment).round(2)
        as_small_business = (rental_income * c.combined_sbd).round(2)
        diff = (as_investment - as_small_business).round(2)
        return SIBCostComparison(
            rental_income=rental_income.round(2),
            tax_as_investment=as_investment,
            tax_as_small_business=as_small_business,
            annual_difference=diff,
            note=(
                f"Rental income taxed as investment income costs {diff.format()} more per year "
                f"than the small-business rate. Active-business treatment requires >5 full-time "
                f"employees; weigh the extra payroll against this saving. Note the refundable "
                f"portion ({c.rdtoh_refundable_rate*100:.2f}%) is recovered only when taxable "
                f"dividends are paid out."
            ),
        )

    # -- corporate tax instalments ------------------------------------------
    def corporate_instalments(
        self, prior_year_tax: Money, *, eligible_for_quarterly: bool = True
    ) -> dict[str, Money]:
        """Required instalments based on the prior-year tax (a common safe-harbour base).

        Small CCPCs meeting the conditions may remit **quarterly**; otherwise **monthly**.
        """
        if eligible_for_quarterly:
            per = (prior_year_tax / 4).round(2)
            return {f"Q{i+1}": per for i in range(4)}
        per = (prior_year_tax / 12).round(2)
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return {m: per for m in months}
