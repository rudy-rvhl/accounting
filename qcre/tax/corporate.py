"""Corporate income tax for a Quebec CCPC holding real estate.

The decisive question for a real-estate corporation is **how the income is characterized**:

* **Rental income is a "specified investment business" (SIB)** — i.e. *investment* income,
  ineligible for the small business deduction — *unless* the corporation employs **more
  than five full-time employees** in the business (citation 'sib'). Most landlords fail
  this, so their rental profit is taxed at the high investment rate (≈ 50.17% combined).
* Even where income *is* active and within the $500k business limit, the **Quebec** half
  of the small business deduction is only available if the corporation meets the **5,500
  paid-hours test** (prorated 5,000–5,500; nil below 5,000) — citation 'quebec_sbd_hours'.
* Investment income carries a **refundable** component: 30.67% of aggregate investment
  income goes to RDTOH, Part IV tax of 38.33% applies to portfolio dividends, and a
  **dividend refund** of 38.33% of taxable dividends paid is recovered from RDTOH
  (citation 'rdtoh').
* The non-taxable half of capital gains feeds the **Capital Dividend Account** (CDA).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcre.core.money import Money
from qcre.tax.rates import RateBook, get_ratebook


@dataclass
class CorporateIncome:
    """Income components for a taxation year (all amounts net of related expenses)."""
    rental_income: Money = field(default_factory=Money.zero)
    other_active_income: Money = field(default_factory=Money.zero)   # e.g. 3rd-party mgmt, development
    interest_income: Money = field(default_factory=Money.zero)
    taxable_capital_gains: Money = field(default_factory=Money.zero)
    portfolio_dividends: Money = field(default_factory=Money.zero)   # from non-connected corps (Part IV)


@dataclass
class CorporateProfile:
    full_time_employees: int = 0                 # >5 makes rental an active business
    quebec_paid_hours: Decimal = Decimal("0")    # for the Quebec SBD hours test
    is_ccpc: bool = True
    taxable_capital_prev_year: Money = field(default_factory=Money.zero)  # SBD grind ($10M-$50M)
    sbd_limit: Money | None = None               # business limit (default $500k; lower if shared)
    is_primary_or_manufacturing: bool = False    # exempt from the Quebec hours test


@dataclass(frozen=True)
class CorporateTaxResult:
    sbd_income: Money
    general_active_income: Money
    aggregate_investment_income: Money
    tax_sbd: Money
    tax_general: Money
    tax_investment: Money
    part_iv_tax: Money
    total_tax: Money
    refundable_tax_added_to_rdtoh: Money
    rental_is_sib: bool
    quebec_sbd_factor: Decimal
    effective_sbd_rate: Decimal
    breakdown: list[tuple[str, Money]]
    notes: list[str] = field(default_factory=list)

    @property
    def average_rate(self) -> Decimal:
        income = (self.sbd_income + self.general_active_income +
                  self.aggregate_investment_income)
        return (self.total_tax.amount / income.amount) if income.is_positive() else Decimal(0)


class CorporateTaxEngine:
    def __init__(self, ratebook: RateBook | None = None) -> None:
        self.rb = ratebook or get_ratebook()

    # -- Quebec small-business-deduction paid-hours test --------------------
    def quebec_sbd_factor(self, profile: CorporateProfile) -> Decimal:
        c = self.rb.corporate
        if profile.is_primary_or_manufacturing:
            return Decimal(1)
        hours = profile.quebec_paid_hours
        if hours >= c.quebec_sbd_hours_full:
            return Decimal(1)
        if hours <= c.quebec_sbd_hours_floor:
            return Decimal(0)
        span = c.quebec_sbd_hours_full - c.quebec_sbd_hours_floor
        return (hours - c.quebec_sbd_hours_floor) / span

    def _sbd_limit(self, profile: CorporateProfile) -> Money:
        c = self.rb.corporate
        limit = profile.sbd_limit or c.sbd_business_limit
        # Large-corporation grind: linear reduction between $10M and $50M of taxable capital.
        tc = profile.taxable_capital_prev_year
        if tc > c.taxable_capital_lower:
            if tc >= c.taxable_capital_upper:
                return Money.zero()
            span = c.taxable_capital_upper - c.taxable_capital_lower
            reduction_frac = (tc - c.taxable_capital_lower).amount / span.amount
            limit = limit * (Decimal(1) - reduction_frac)
        return limit.round(2)

    def compute(
        self, income: CorporateIncome, profile: CorporateProfile | None = None
    ) -> CorporateTaxResult:
        c = self.rb.corporate
        profile = profile or CorporateProfile()
        notes: list[str] = []

        # 1. Characterize rental income (SIB unless >5 full-time employees).
        rental_is_sib = profile.full_time_employees <= c.sib_max_full_time_employees
        if rental_is_sib and income.rental_income.is_positive():
            notes.append(
                f"Rental income treated as investment income (specified investment business): "
                f"only {profile.full_time_employees} full-time employee(s) (>5 needed for active "
                f"business). Taxed at ≈{c.combined_investment*100:.2f}% rather than the small "
                f"business rate."
            )

        active_for_sbd = income.other_active_income
        if not rental_is_sib:
            active_for_sbd = active_for_sbd + income.rental_income

        aii = income.interest_income + income.taxable_capital_gains
        if rental_is_sib:
            aii = aii + income.rental_income
        aii = aii.round(2)

        # 2. Small business deduction.
        if not profile.is_ccpc:
            sbd_income = Money.zero()
            notes.append("Not a CCPC — small business deduction unavailable.")
        else:
            sbd_income = min(active_for_sbd, self._sbd_limit(profile), key=lambda m: m.amount)
        sbd_income = max(sbd_income, Money.zero(), key=lambda m: m.amount)
        general_active = (active_for_sbd - sbd_income).round(2)

        qc_factor = self.quebec_sbd_factor(profile)
        quebec_rate_on_sbd = c.quebec_general - qc_factor * (c.quebec_general - c.quebec_sbd)
        effective_sbd_rate = (c.federal_sbd + quebec_rate_on_sbd)
        if income.other_active_income.is_positive() or not rental_is_sib:
            if qc_factor < 1:
                notes.append(
                    f"Quebec small business deduction reduced: {profile.quebec_paid_hours} paid "
                    f"hours vs 5,500 required (factor {qc_factor:.2f}). Effective small-business "
                    f"rate {effective_sbd_rate*100:.2f}%."
                )

        # 3. Tax on each layer.
        tax_sbd = (sbd_income * effective_sbd_rate).round(2)
        tax_general = (general_active * c.combined_general).round(2)
        tax_investment = (aii * c.combined_investment).round(2)
        part_iv = (income.portfolio_dividends * c.part_iv_rate).round(2)

        total_tax = (tax_sbd + tax_general + tax_investment + part_iv).round(2)

        # 4. Refundable component added to RDTOH.
        refundable = (aii * c.rdtoh_refundable_rate + part_iv).round(2)

        breakdown = [
            (f"Small business income @ {effective_sbd_rate*100:.2f}%", tax_sbd),
            (f"General active income @ {c.combined_general*100:.2f}%", tax_general),
            (f"Investment income @ {c.combined_investment*100:.2f}%", tax_investment),
            (f"Part IV tax on portfolio dividends @ {c.part_iv_rate*100:.2f}%", part_iv),
        ]

        return CorporateTaxResult(
            sbd_income=sbd_income,
            general_active_income=general_active,
            aggregate_investment_income=aii,
            tax_sbd=tax_sbd,
            tax_general=tax_general,
            tax_investment=tax_investment,
            part_iv_tax=part_iv,
            total_tax=total_tax,
            refundable_tax_added_to_rdtoh=refundable,
            rental_is_sib=rental_is_sib,
            quebec_sbd_factor=qc_factor,
            effective_sbd_rate=effective_sbd_rate,
            breakdown=breakdown,
            notes=notes,
        )

    def dividend_refund(self, taxable_dividends_paid: Money, rdtoh_balance: Money) -> Money:
        """Refund on paying taxable dividends: lesser of 38.33% of dividends and RDTOH."""
        c = self.rb.corporate
        potential = (taxable_dividends_paid * c.dividend_refund_rate).round(2)
        return min(potential, rdtoh_balance, key=lambda m: m.amount)
