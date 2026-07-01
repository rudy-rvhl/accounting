"""Rate-book data structures shared across taxation years.

A ``RateBook`` is an immutable snapshot of every Quebec/Canada tax parameter the engine
needs for one taxation year, each carrying a :class:`Citation` so the figure can be
traced to its source. ``BracketTable`` implements progressive bracket math used for both
personal income tax and property transfer duties.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcre.core.money import Money


@dataclass(frozen=True)
class Citation:
    topic: str
    source: str
    url: str
    effective: str
    note: str = ""


@dataclass(frozen=True)
class Bracket:
    """A marginal bracket: *rate* applies to income/value between the previous threshold
    and ``up_to`` (``None`` means no upper limit)."""

    up_to: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class BracketTable:
    brackets: tuple[Bracket, ...]

    def tax_on(self, base: Money) -> Money:
        """Progressive tax/duty on *base*."""
        remaining = base.amount
        if remaining <= 0:
            return Money.zero()
        tax = Decimal(0)
        lower = Decimal(0)
        for br in self.brackets:
            upper = br.up_to if br.up_to is not None else remaining + lower
            slice_amount = min(base.amount, upper) - lower
            if slice_amount <= 0:
                break
            tax += slice_amount * br.rate
            lower = upper
            if base.amount <= upper:
                break
        return Money(tax)

    def marginal_rate(self, base: Money) -> Decimal:
        lower = Decimal(0)
        for br in self.brackets:
            if br.up_to is None or base.amount <= br.up_to:
                return br.rate
            lower = br.up_to
        return self.brackets[-1].rate

    def average_rate(self, base: Money) -> Decimal:
        if base.amount <= 0:
            return Decimal(0)
        return (self.tax_on(base).amount / base.amount)


@dataclass(frozen=True)
class SalesTaxRates:
    gst: Decimal              # 0.05
    qst: Decimal              # 0.09975
    registration_threshold: Money

    @property
    def combined(self) -> Decimal:
        return self.gst + self.qst


@dataclass(frozen=True)
class CorporateRates:
    # Combined federal + Quebec rates (the numbers a CFO actually plans around)...
    combined_sbd: Decimal          # small business rate (active income, if it qualifies)
    combined_general: Decimal      # general active business income
    combined_investment: Decimal   # aggregate investment income (incl. SIB rental)
    # ...and the components, for transparency / schedule rebuilds.
    federal_sbd: Decimal
    federal_general: Decimal
    federal_investment: Decimal
    quebec_sbd: Decimal
    quebec_general: Decimal
    quebec_investment: Decimal
    # Small business deduction parameters.
    sbd_business_limit: Money              # $500,000 federal business limit
    taxable_capital_lower: Money           # $10M — SBD grind begins
    taxable_capital_upper: Money           # $50M — SBD fully ground out
    quebec_sbd_hours_full: Decimal         # 5,500 paid hours for full Quebec SBD
    quebec_sbd_hours_floor: Decimal        # 5,000 paid hours — below this, no Quebec SBD
    sib_max_full_time_employees: int       # >5 FTE escapes specified-investment-business
    # Refundable mechanism on investment income (CCPC).
    rdtoh_refundable_rate: Decimal         # 30.67% of AII added to non-eligible RDTOH
    part_iv_rate: Decimal                  # 38.33% on portfolio dividends
    dividend_refund_rate: Decimal          # 38.33% of taxable dividends paid, refunded
    cda_inclusion: Decimal                 # non-taxable half of capital gains -> CDA (0.5)


@dataclass(frozen=True)
class CapitalGainsRates:
    inclusion_rate: Decimal                # 0.50 for 2025/2026
    lifetime_exemption_qsbc: Money         # $1.25M (does NOT apply to rental real estate)


@dataclass(frozen=True)
class DividendParams:
    eligible_gross_up: Decimal
    non_eligible_gross_up: Decimal
    federal_dtc_eligible: Decimal          # of grossed-up dividend
    federal_dtc_non_eligible: Decimal
    quebec_dtc_eligible: Decimal
    quebec_dtc_non_eligible: Decimal


@dataclass(frozen=True)
class PersonalRates:
    federal: BracketTable
    quebec: BracketTable
    quebec_abatement: Decimal              # 16.5% reduction of basic federal tax
    federal_bpa: Money                     # basic personal amount (simplified, top value)
    quebec_bpa: Money
    federal_lowest_rate: Decimal           # rate at which non-refundable credits are valued
    quebec_lowest_rate: Decimal
    top_combined_rate: Decimal             # convenience: top marginal rate (TOSI uses this)


@dataclass(frozen=True)
class TransferDutyRates:
    standard: BracketTable
    montreal: BracketTable
    note: str = ""


@dataclass(frozen=True)
class TrustParams:
    deemed_disposition_years: int          # 21-year rule
    taxed_at_top_rate: bool                # inter-vivos trust taxed at top marginal rate
    tosi_top_rate: Decimal                 # split income taxed at top marginal rate


@dataclass(frozen=True)
class CCAClass:
    number: str
    rate: Decimal                          # declining-balance rate (0 for straight-line classes)
    description: str
    straight_line: bool = False
    accelerated_first_year_factor: Decimal | None = None  # AII enhanced first-year multiple


@dataclass(frozen=True)
class CCARates:
    classes: dict[str, CCAClass]
    half_year_rule: bool
    aii_first_year_uplift: Decimal         # enhanced first-year CCA uplift (phase-out value)
    rental_loss_restriction: bool          # CCA cannot create/increase a rental loss


@dataclass(frozen=True)
class RateBook:
    year: int
    sales_tax: SalesTaxRates
    corporate: CorporateRates
    capital_gains: CapitalGainsRates
    dividends: DividendParams
    personal: PersonalRates
    transfer_duty: TransferDutyRates
    trust: TrustParams
    cca: CCARates
    citations: tuple[Citation, ...] = field(default_factory=tuple)

    def citation(self, topic: str) -> Citation | None:
        for c in self.citations:
            if c.topic == topic:
                return c
        return None
